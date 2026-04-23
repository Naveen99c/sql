# PHASE 0 — The Mental Model

> *Before writing any SQL, understand how the engine thinks.*

---

## 0.1 SQL Logical Order of Execution

Many bugs come from assuming `SELECT` runs before `WHERE`.

```
1. FROM / JOIN    → Assemble the raw data set
2. WHERE          → Filter individual rows
3. GROUP BY       → Collapse rows into groups
4. HAVING         → Filter groups
5. SELECT         → Evaluate expressions, aliases
6. DISTINCT       → Remove duplicate rows
7. ORDER BY       → Sort (first place aliases are usable)
8. LIMIT / OFFSET → Truncate the result
```

🧠 **Why this matters:**
- You **cannot** reference a `SELECT` alias in `WHERE` — `WHERE` runs first.
- You **can** reference it in `ORDER BY` — `ORDER BY` runs after `SELECT`.
- Window functions run during `SELECT`, so you cannot filter on them in `WHERE` — wrap in a CTE first.
- `HAVING` can use aggregate expressions; `WHERE` cannot.

**Can I use a SELECT alias here?**

| Clause | Alias usable? | Notes |
|---|---|---|
| `WHERE` | ❌ | Runs before `SELECT`. Repeat the expression or wrap in a subquery/CTE. |
| `GROUP BY` | ⚠️ Engine-specific | MySQL/PostgreSQL allow it; SQL Server/Oracle do not. |
| `HAVING` | ⚠️ Engine-specific | MySQL allows; ANSI forbids. Safest: repeat the aggregate. |
| `SELECT` (same list) | ❌ | Cannot reference a sibling alias; use a CTE or subquery. |
| `ORDER BY` | ✅ | Runs after `SELECT`; aliases and positional numbers both work. |
| `LIMIT` / `OFFSET` | ✅ | Runs last. |

---

## 0.2 NULL Semantics & Three-Valued Logic

SQL uses **TRUE / FALSE / UNKNOWN** — not just true/false. Any comparison involving NULL yields UNKNOWN.

```
NULL = NULL      → UNKNOWN  (not TRUE!)
NULL <> NULL     → UNKNOWN  (not TRUE!)
NULL > 5         → UNKNOWN
NOT UNKNOWN      → UNKNOWN
TRUE AND UNKNOWN → UNKNOWN
TRUE OR UNKNOWN  → TRUE
FALSE AND UNKNOWN → FALSE
```

🧠 **The golden rule:** NULL means "unknown/missing." You can't compare an unknown to anything — the result is unknown.

⚠️ **WHERE and HAVING discard UNKNOWN:** Only rows where the condition is TRUE pass through. `WHERE col = NULL` returns **zero rows**, even if NULLs exist.

### Correct NULL Checks

```sql
-- WRONG ❌
WHERE col = NULL
WHERE col != NULL

-- RIGHT ✅
WHERE col IS NULL
WHERE col IS NOT NULL
```

### NULL Behavior Across Operations

| Context | NULL Behavior | Surprise Factor |
|---|---|---|
| `=`, `<>`, `<`, `>` | Any comparison with NULL → UNKNOWN | 🔴 High |
| `IN (1, 2, NULL)` | `3 IN (1, 2, NULL)` → UNKNOWN, not FALSE | 🔴 High |
| `NOT IN (1, 2, NULL)` | **Always UNKNOWN** → returns NO rows | 🔴 Critical |
| `COUNT(*)` | Counts all rows including NULLs | 🟡 Medium |
| `COUNT(col)` | Skips NULL values | 🟡 Medium |
| `SUM`, `AVG`, `MIN`, `MAX` | Skip NULLs entirely | 🟡 Medium |
| `AVG` denominator | NULLs excluded from count | 🔴 High |
| `GROUP BY` | NULLs grouped together (same group) | 🟡 Medium |
| `ORDER BY` | NULLs first or last (engine-dependent) | 🟡 Medium |
| `DISTINCT` | Multiple NULLs collapse to one NULL | 🟡 Medium |
| `UNION` | NULL = NULL for dedup purposes | 🔴 Contradicts `=` behavior |
| `CONCAT('a', NULL)` | Returns NULL (MySQL); 'a' (PostgreSQL `\|\|`) | 🔴 Engine-specific |
| Arithmetic: `5 + NULL` | NULL | 🟡 Medium |
| `CASE WHEN NULL THEN ...` | Falls through to ELSE | 🟡 Medium |

### NOT IN vs NOT EXISTS — The NULL Disaster

```sql
-- Subquery returns: (1, 2, NULL)
-- Query: WHERE id NOT IN (1, 2, NULL)
-- Evaluates: id <> 1 AND id <> 2 AND id <> NULL
--          = TRUE    AND TRUE    AND UNKNOWN
--          = UNKNOWN → row excluded!
-- Result: ZERO rows returned, no matter what!
```

Fix: always add `WHERE col IS NOT NULL` in the subquery, or use `NOT EXISTS`.

### NULL-Handling Functions

| Function | Behavior | Engine |
|---|---|---|
| `COALESCE(a, b, c)` | Returns first non-NULL value | All (ANSI SQL) |
| `IFNULL(a, b)` | If a is NULL, return b | MySQL |
| `ISNULL(a, b)` | If a is NULL, return b | SQL Server |
| `NVL(a, b)` | If a is NULL, return b | Oracle |
| `NULLIF(a, b)` | Returns NULL if a = b, else a | All |

```sql
-- COALESCE: chain of fallbacks
SELECT COALESCE(preferred_name, first_name, 'Unknown') AS display_name
FROM users;

-- NULLIF: prevent division by zero
SELECT revenue / NULLIF(cost, 0) AS ratio   -- returns NULL instead of error
FROM financials;

-- Replace NULL in AVG calculation
SELECT AVG(COALESCE(rating, 0)) AS avg_with_zeros  -- treats NULL as 0
FROM reviews;
```

### NULL in JOINs

```sql
-- NULL keys NEVER match in joins (NULL = NULL → UNKNOWN → no match)
SELECT *
FROM table_a a
JOIN table_b b ON a.key = b.key;   -- rows where a.key IS NULL are excluded
```

💡 If you need NULLs to match:
```sql
ON (a.key = b.key OR (a.key IS NULL AND b.key IS NULL))
-- Or: ON a.key IS NOT DISTINCT FROM b.key  (PostgreSQL)
```

💡 **`IS [NOT] DISTINCT FROM` — null-safe equality.** `a IS NOT DISTINCT FROM b` is `TRUE` when either both are equal **or** both are NULL — never UNKNOWN. Cleaner than the `OR (… IS NULL AND … IS NULL)` workaround. Supported by PostgreSQL, SQL Server 2022+, and BigQuery/Snowflake. MySQL has the `<=>` operator for the same semantics.

### ORDER BY with NULLs

```sql
-- MySQL: NULLs sort FIRST in ASC, LAST in DESC
-- PostgreSQL: NULLs sort LAST in ASC, FIRST in DESC (opposite!)

-- PostgreSQL: Control explicitly
ORDER BY col ASC NULLS LAST
ORDER BY col DESC NULLS FIRST

-- MySQL workaround:
ORDER BY col IS NULL, col ASC   -- pushes NULLs to end
```

---

## 0.3 Type Casting & Implicit Conversions

⚠️ When you compare values of different types, SQL silently converts one. This causes:
1. **Wrong results** (string `'10' < '9'` lexicographically)
2. **Index bypass** (function on column = no index)

```sql
-- TRAP: varchar compared to int → MySQL converts VARCHAR to number
WHERE phone_number = 12345     -- converts '012345' to 12345, matches!
WHERE phone_number = '012345'  -- correct string comparison

-- TRAP: date compared to string
WHERE created_at = '2024-01-15'   -- OK: implicit cast to date
WHERE created_at = '01/15/2024'   -- Risky: format may not parse correctly
```

### Explicit Casting

```sql
-- ANSI SQL
CAST(expression AS target_type)

-- MySQL
CAST('123' AS UNSIGNED)
CAST('2024-01-01' AS DATE)
CONVERT(expr, type)

-- PostgreSQL
expression::target_type       -- shorthand
CAST(expression AS INTEGER)

-- Common use: force integer division to return decimal
SELECT CAST(a AS DECIMAL) / b    -- instead of a / b (integer division!)
SELECT a * 1.0 / b               -- alternative trick
```

⚠️ **Integer division trap:**
```sql
SELECT 7 / 2        -- MySQL: 3.5000 | PostgreSQL: 3 | SQL Server: 3
SELECT 7 / 2.0      -- All: 3.5
SELECT CAST(7 AS DECIMAL) / 2  -- All: 3.5
```

---

## 0.4 CASE Expressions

```sql
-- Simple CASE
CASE status
    WHEN 'A' THEN 'Active'
    WHEN 'I' THEN 'Inactive'
    ELSE 'Unknown'
END

-- Searched CASE (more flexible)
CASE
    WHEN salary > 100000 THEN 'High'
    WHEN salary > 50000  THEN 'Medium'
    ELSE 'Low'
END
```

⚙️ CASE is an **expression**, not a statement — it returns a value and can appear in SELECT, WHERE, ORDER BY, GROUP BY, and inside aggregate functions.

⚠️ `CASE col WHEN NULL` **never matches** — use `CASE WHEN col IS NULL` instead.

---

## 0.5 BETWEEN & DISTINCT Nuances

### BETWEEN

```sql
-- BETWEEN is inclusive: includes both endpoints
WHERE id BETWEEN 1 AND 5      -- same as id >= 1 AND id <= 5

-- ⚠️ TIMESTAMP trap:
WHERE created_at BETWEEN '2024-01-01' AND '2024-01-31'
-- MISSES timestamps like '2024-01-31 15:30:00' because
-- '2024-01-31' is interpreted as '2024-01-31 00:00:00'

-- Fix:
WHERE created_at >= '2024-01-01' AND created_at < '2024-02-01'
```

### DISTINCT

```sql
-- DISTINCT applies to the ENTIRE SELECT list
SELECT DISTINCT department, status FROM employees;
-- Deduplicates (department, status) PAIRS — not just department

-- DISTINCT inside aggregate: different behavior
SELECT COUNT(DISTINCT department) FROM employees;  -- count of unique departments
SELECT COUNT(department) FROM employees;           -- count of non-NULL values

-- DISTINCT with ORDER BY: ORDER BY columns must appear in SELECT (some engines)
SELECT DISTINCT department FROM employees ORDER BY department;  -- OK
SELECT DISTINCT department FROM employees ORDER BY salary;      -- ERROR in PostgreSQL
```

---

## 0.6 Operator Precedence & Parentheses

⚠️ **`AND` binds tighter than `OR`.** Without parentheses, `WHERE a = 1 OR b = 2 AND c = 3` parses as `WHERE a = 1 OR (b = 2 AND c = 3)` — almost never what was intended.

```sql
-- BUG: reads as "active, OR (premium AND recent)"
WHERE status = 'active' OR plan = 'premium' AND signup_date > '2024-01-01'

-- FIX: parenthesize the OR group
WHERE (status = 'active' OR plan = 'premium') AND signup_date > '2024-01-01'
```

**Precedence (tightest → loosest):** `()` → unary `-`, `NOT` → `*`, `/`, `%` → `+`, `-` → comparison (`=`, `<`, `>`, `LIKE`, `IN`, `BETWEEN`) → `AND` → `OR`.

💡 **Rule of thumb:** whenever you mix `AND` and `OR`, parenthesize explicitly — even when the default grouping is what you want. It makes intent obvious in code review.

---
---

# PHASE 1 — Schema & Data Modeling

> *Understand the tables before querying them. Know your data types, constraints, and what the schema guarantees.*

---

## 1.1 Data Type Nuances

### String Types

| Type | Storage | Behavior |
|---|---|---|
| `CHAR(n)` | Fixed-width, padded with spaces | Comparisons ignore trailing spaces (MySQL) |
| `VARCHAR(n)` | Variable-width, up to n chars | No padding; stores actual length |
| `TEXT` / `CLOB` | Variable-width, very large | Cannot be indexed directly (MySQL); use prefix index |

⚠️ **CHAR vs VARCHAR trap:**
```sql
-- MySQL: CHAR(5) 'abc' stored as 'abc  ' — trailing spaces ignored in comparisons
WHERE char_col = 'abc'    -- matches 'abc  '
WHERE char_col = 'abc  '  -- also matches 'abc  '

-- But LENGTH differs:
SELECT LENGTH(char_col)    -- 3 (spaces trimmed in many contexts)
```

💡 **Rule:** Use `VARCHAR` for almost everything. `CHAR` only for fixed-length codes (country codes, UUIDs).

### Numeric Types

| Type | Precision | Use Case |
|---|---|---|
| `INT` / `BIGINT` | Exact integers | IDs, counts |
| `DECIMAL(p, s)` / `NUMERIC(p, s)` | Exact fixed-point | Money, rates — **never use FLOAT for money** |
| `FLOAT` / `DOUBLE` | Approximate floating-point | Scientific data, when precision loss is acceptable |

⚠️ **FLOAT precision trap:**
```sql
-- FLOAT loses precision
SELECT CAST(0.1 + 0.2 AS FLOAT);        -- 0.30000000000000004 (not 0.3!)
SELECT CAST(0.1 + 0.2 AS DECIMAL(10,2)); -- 0.30 (exact)

-- NEVER compare FLOATs with =
WHERE float_col = 0.3         -- ❌ may not match
WHERE ABS(float_col - 0.3) < 0.0001  -- ✅ epsilon comparison
```

### Date/Time Types

| Type | Stores | Range |
|---|---|---|
| `DATE` | Date only (no time) | '1000-01-01' to '9999-12-31' |
| `DATETIME` / `TIMESTAMP` | Date + time | TIMESTAMP auto-converts to UTC (MySQL) |
| `TIME` | Time only | '-838:59:59' to '838:59:59' (MySQL) |
| `INTERVAL` | Duration | PostgreSQL native; no direct MySQL equivalent |

⚠️ **DATETIME vs TIMESTAMP (MySQL):**
- `TIMESTAMP`: stored as UTC, converted to session timezone on retrieval. Range: 1970–2038.
- `DATETIME`: stored as-is, no timezone conversion. Range: 1000–9999.

---

## 1.2 Constraints & Referential Integrity

### Constraint Types

| Constraint | Purpose | Example |
|---|---|---|
| `PRIMARY KEY` | Uniquely identifies each row; NOT NULL + UNIQUE | `id INT PRIMARY KEY` |
| `FOREIGN KEY` | References a row in another table | `REFERENCES departments(id)` |
| `UNIQUE` | No duplicate values (NULLs allowed — multiple NULLs OK in most engines) | `UNIQUE(email)` |
| `NOT NULL` | Column cannot be NULL | `name VARCHAR(100) NOT NULL` |
| `CHECK` | Custom validation | `CHECK (age >= 0 AND age <= 150)` |
| `DEFAULT` | Value when not specified | `DEFAULT CURRENT_TIMESTAMP` |

💡 **Generated / computed columns.** A column whose value is always derived from other columns in the same row.
```sql
-- MySQL / PostgreSQL 12+ / SQL Server
full_name VARCHAR(200) GENERATED ALWAYS AS (CONCAT(first_name, ' ', last_name)) STORED
-- VIRTUAL  = recomputed on read (no disk use, cannot be indexed in MySQL InnoDB)
-- STORED   = materialized on write (disk cost, indexable)
```
Used heavily for functional indexes (see §5.4 JSON indexing) and for denormalizing derived fields safely.

### Foreign Key Actions

```sql
CREATE TABLE orders (
    id INT PRIMARY KEY,
    customer_id INT,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
        ON DELETE CASCADE        -- delete orders when customer deleted
        ON UPDATE SET NULL       -- set to NULL when customer id changes
);
```

| Action | ON DELETE | ON UPDATE |
|---|---|---|
| `CASCADE` | Delete child rows | Update child foreign keys |
| `SET NULL` | Set FK to NULL | Set FK to NULL |
| `SET DEFAULT` | Set FK to default value | Set FK to default value |
| `RESTRICT` / `NO ACTION` | Block parent delete | Block parent update |

🧠 **Interview relevance:** Understanding constraints explains why certain JOINs always match (FK guarantees existence) and why anti-joins find orphaned rows.

---

## 1.3 Normalization (Quick Reference)

| Normal Form | Rule | Violation Example | Fix |
|---|---|---|---|
| **1NF** | No repeating groups or arrays in a cell | `tags = 'sql,python,java'` | Separate table `user_tags` |
| **2NF** | Every non-key column depends on the **entire** PK | Composite PK `(order_id, product_id)` with `customer_name` depending only on `order_id` | Move `customer_name` to `orders` table |
| **3NF** | No transitive dependencies (non-key → non-key) | `employee` table with `dept_id`, `dept_name` (dept_name depends on dept_id, not employee) | Move `dept_name` to `departments` table |

🧠 **When to denormalize:** Reporting tables, data warehouses, and high-read/low-write scenarios benefit from denormalization to avoid expensive JOINs.

### Surrogate vs Natural Keys

| Key type | Example | Pros | Cons |
|---|---|---|---|
| **Natural** | `email`, `ssn`, `isbn` | Meaningful; no extra column | Can change (email updates); may leak PII; composite keys bloat FKs |
| **Surrogate** | `id SERIAL`, `UUID` | Immutable; compact FKs; decoupled from business rules | Opaque; still need UNIQUE on the natural key to prevent dup rows |

💡 **Default:** surrogate PK + a `UNIQUE` constraint on the business-natural key. Interviewers often probe on "what if the email changes?" — the surrogate answer is the clean one.

---

## 1.4 Engine Differences — MySQL vs PostgreSQL vs SQL Server

| Feature | MySQL | PostgreSQL | SQL Server |
|---|---|---|---|
| Recursive CTE keyword | `WITH RECURSIVE` | `WITH RECURSIVE` | `WITH` (no RECURSIVE keyword) |
| String concat operator | `CONCAT()` | `\|\|` | `+` |
| LIMIT syntax | `LIMIT n` | `LIMIT n` | `TOP n` or `FETCH FIRST n` |
| BOOL type | `TINYINT(1)` | Native `BOOLEAN` | `BIT` |
| Auto-increment | `AUTO_INCREMENT` | `SERIAL` / `GENERATED` | `IDENTITY` |
| FULL OUTER JOIN | ❌ Not supported | ✅ | ✅ |
| LATERAL JOIN | ❌ (MySQL 8.0.14+: `LATERAL`) | ✅ | `CROSS APPLY` / `OUTER APPLY` |
| NULLs in ORDER BY | NULLs first (ASC) | NULLs last (ASC) | NULLs first (ASC) |
| Integer division | Returns decimal | Truncates to int | Truncates to int |
| String agg | `GROUP_CONCAT` | `STRING_AGG` | `STRING_AGG` (2017+) |
| `IF` in query | `IF(cond, a, b)` | ❌ (use `CASE`) | `IIF(cond, a, b)` |
| `QUALIFY` (filter on window result — Snowflake/BigQuery/Databricks/Teradata) | ❌ | ❌ | ❌ |

---
---

# PHASE 2 — Core Query Patterns

> *The bread and butter. Every SQL interview question uses at least one of these.*

---

## 2.1 Aggregation + GROUP BY + HAVING

### What It Is

The foundational pattern: collapse rows into groups, compute summaries, and filter on those summaries.

### Technical Mechanics

⚙️ **GROUP BY execution:**

1. Engine scans rows matching WHERE.
2. Groups rows with identical GROUP BY column values.
3. For each group, computes aggregate functions.
4. HAVING filters groups based on aggregate results.
5. SELECT outputs the surviving groups.

**Rules:**
- Every column in SELECT must be in GROUP BY or inside an aggregate function.
- HAVING can reference aggregate expressions; WHERE cannot.

### Aggregate Functions Deep Dive

| Function | Returns | NULL handling |
|---|---|---|
| `COUNT(*)` | Number of rows | Counts NULLs |
| `COUNT(col)` | Number of non-NULL values | Skips NULLs |
| `COUNT(DISTINCT col)` | Number of unique non-NULL values | Skips NULLs |
| `SUM(col)` | Sum | Ignores NULLs; returns NULL if all NULL |
| `AVG(col)` | Average | Ignores NULLs (doesn't count them in denominator!) |
| `MIN(col)` / `MAX(col)` | Min / Max | Ignores NULLs |

⚠️ **AVG pitfall:** `AVG` does not count NULL values in the denominator. If you have values (10, NULL, 30), `AVG = (10+30)/2 = 20`, not `(10+0+30)/3 = 13.3`. Use `AVG(COALESCE(col, 0))` if NULLs should be treated as zeros.

### Sub-Pattern A — Conditional Aggregation

🧠 *"Count or sum only rows meeting a condition, without filtering out others."*

```sql
SELECT
    department,
    COUNT(*) AS total_emp,
    COUNT(CASE WHEN status = 'active' THEN 1 END) AS active_emp,
    SUM(CASE WHEN gender = 'F' THEN salary ELSE 0 END) AS female_salary_total,
    ROUND(100.0 * COUNT(CASE WHEN status = 'active' THEN 1 END) / COUNT(*), 1) AS active_pct
FROM employees
GROUP BY department;
```

💡 `FILTER (WHERE ...)` is the PostgreSQL-specific cleaner syntax:
```sql
COUNT(*) FILTER (WHERE status = 'active') AS active_emp
```

### Sub-Pattern B — HAVING for Group Filtering

```sql
-- Customers with 3+ orders totaling > $1000
SELECT customer_id, COUNT(*) AS order_count, SUM(amount) AS total_spent
FROM orders
GROUP BY customer_id
HAVING COUNT(*) >= 3 AND SUM(amount) > 1000;
```

### Sub-Pattern C — "Bought All Products" (Relational Division)

🧠 *"Find customers who ordered every product in the products table."*

This is **relational division** — COUNT DISTINCT items = total items.

```sql
SELECT customer_id
FROM orders
GROUP BY customer_id
HAVING COUNT(DISTINCT product_key) = (SELECT COUNT(*) FROM products);
```

💡 **Alternative: double `NOT EXISTS`** (classic relational-algebra phrasing). Read as: "no product exists that this customer has not ordered."
```sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1 FROM products p
    WHERE NOT EXISTS (
        SELECT 1 FROM orders o
        WHERE o.customer_id = c.customer_id
          AND o.product_key = p.product_key
    )
);
```
FAANG interviewers often ask for *both* phrasings. The count-based version is usually faster; the double-NOT-EXISTS version is more general (handles conditional matches, not just equality).

### Sub-Pattern D — Ratio / Percentage Calculation

```sql
SELECT
    DATE_FORMAT(order_date, '%Y-%m') AS month,
    ROUND(
        100.0 * SUM(CASE WHEN status = 'returned' THEN 1 ELSE 0 END) / COUNT(*),
        2
    ) AS return_rate
FROM orders
GROUP BY DATE_FORMAT(order_date, '%Y-%m');
```

### 📝 Sample Problem — Duplicate Emails

> Table `Person(id, email)`. Find all duplicate emails.

```sql
SELECT email
FROM Person
GROUP BY email
HAVING COUNT(*) > 1;
```

**Why GROUP BY + HAVING?** GROUP BY collapses all rows with the same email; HAVING filters to only groups with more than one row.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Duplicate Emails | Easy | [▶ Practice](sql_sandbox.html?slug=duplicate-emails) |
| 2 | Classes More Than 5 Students | Easy | [▶ Practice](sql_sandbox.html?slug=classes-more-than-5-students) |
| 3 | Number of Unique Categories | Easy | [▶ Practice](sql_sandbox.html?slug=number-of-unique-categories) |
| 4 | Average Selling Price | Easy | [▶ Practice](sql_sandbox.html?slug=average-selling-price) |
| 5 | Customers Who Bought All Products | Medium | [▶ Practice](sql_sandbox.html?slug=customers-who-bought-all-products) |
| 6 | Immediate Food Delivery II | Medium | [▶ Practice](sql_sandbox.html?slug=immediate-food-delivery-ii) |
| 7 | Count Salary Categories | Medium | [▶ Practice](sql_sandbox.html?slug=count-salary-categories) |
| 8 | **Average Salary: Departments vs Company** | Hard | [▶ Practice](sql_sandbox.html?slug=average-salary-departments-vs-company) |

---

## 2.2 Subqueries & CTEs

### What It Is

Break complex logic into modular, readable pieces. CTEs are named temporary result sets; subqueries are inline queries.

### Types of Subqueries

| Type | Location | Cardinality | Correlation |
|---|---|---|---|
| **Scalar** | SELECT, WHERE | 1 row, 1 col | Can be correlated |
| **Row** | WHERE | 1 row, N cols | Usually uncorrelated |
| **Table (Derived)** | FROM | N rows, N cols | Uncorrelated |
| **Correlated** | WHERE, SELECT | Varies | References outer query |
| **EXISTS** | WHERE | Boolean | Always correlated |

⚙️ **Correlated vs Uncorrelated:**

- **Uncorrelated:** Runs once, independently of the outer query. Think of it as a constant.
- **Correlated:** Runs once **per row** of the outer query (conceptually). The optimizer often rewrites it as a join.

### CTE Mechanics

```sql
WITH
    cte1 AS ( SELECT ... ),
    cte2 AS ( SELECT ... FROM cte1 )  -- can reference earlier CTEs
SELECT * FROM cte2;
```

💡 CTEs improve readability but are **not** materialized in most engines (they're inlined like views). Exception: `MATERIALIZED` hint in PostgreSQL.

### Sub-Pattern A — Scalar Subquery for Comparison

🧠 *"I need to compare each row's value to a global or group aggregate."*

```sql
-- Employees earning above company average
SELECT name, salary
FROM employees
WHERE salary > (SELECT AVG(salary) FROM employees);
```

### Sub-Pattern B — Correlated Subquery

🧠 *"For each row, calculate something that depends on that row's context."*

```sql
-- Each employee's salary vs their department average
SELECT
    name,
    salary,
    (SELECT AVG(salary)
     FROM employees e2
     WHERE e2.dept_id = e1.dept_id) AS dept_avg
FROM employees e1;
```

⚠️ Can be slow on large tables. Consider rewriting as a JOIN + GROUP BY or a window function.

### Sub-Pattern C — Multi-Step CTE Pipeline

🧠 *"The problem has multiple stages of transformation."*

```sql
WITH
    -- Step 1: Calculate monthly totals
    monthly AS (
        SELECT user_id, DATE_FORMAT(order_date, '%Y-%m') AS month, SUM(amount) AS total
        FROM orders
        GROUP BY user_id, DATE_FORMAT(order_date, '%Y-%m')
    ),
    -- Step 2: Rank months per user
    ranked AS (
        SELECT *, RANK() OVER (PARTITION BY user_id ORDER BY total DESC) AS rnk
        FROM monthly
    )
-- Step 3: Get top month per user
SELECT user_id, month, total
FROM ranked
WHERE rnk = 1;
```

### 📝 Sample Problem — Exchange Seats

> Table `Seat(id, student)`. Swap every two consecutive students' seats. If odd number of students, last one stays.

```sql
SELECT
    CASE
        WHEN id % 2 = 1 AND id = (SELECT MAX(id) FROM Seat) THEN id
        WHEN id % 2 = 1 THEN id + 1
        ELSE id - 1
    END AS id,
    student
FROM Seat
ORDER BY id;
```

**Intuition:** Odd IDs get +1 (swap with next), even IDs get -1 (swap with previous). The last odd ID (no partner) stays put.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Customers Who Never Order | Easy | [▶ Practice](sql_sandbox.html?slug=customers-who-never-order) |
| 2 | Department Highest Salary | Medium | [▶ Practice](sql_sandbox.html?slug=department-highest-salary) |
| 3 | Exchange Seats | Medium | [▶ Practice](sql_sandbox.html?slug=exchange-seats) |
| 4 | **Median Employee Salary** | Hard | [▶ Practice](sql_sandbox.html?slug=median-employee-salary) |
| 5 | **Game Play Analysis V** | Hard | [▶ Practice](sql_sandbox.html?slug=game-play-analysis-v) |

---

## 2.3 Self-Joins & JOIN Semantics (ON vs WHERE)

### What It Is

Join a table to **itself** to compare rows within the same table. Also: understanding the critical difference between filtering in `ON` vs `WHERE` for outer joins.

### Self-Join Intuition

🧠 *"I need to compare two rows from the same table."*

Think of the table as two copies (alias them `a` and `b`). The join condition defines the relationship between the two copies.

| Scenario | Join Condition |
|---|---|
| Employee vs Manager | `e.manager_id = m.id` |
| Previous day's record | `a.date = DATE_ADD(b.date, INTERVAL 1 DAY)` |
| All pairs | `a.id < b.id` (avoid duplicates + self-pairs) |
| Same group, different row | `a.group = b.group AND a.id <> b.id` |

### ON vs WHERE — The Critical Difference

This only matters for **OUTER JOINS** (LEFT/RIGHT/FULL).

| Clause | When applied | Effect on outer join |
|---|---|---|
| `ON` | During join | Non-matching rows still appear (with NULLs) |
| `WHERE` | After join | Non-matching rows are **eliminated** |

```sql
-- ON: Users without 2024 orders still appear (order columns = NULL)
SELECT u.*, o.order_id
FROM users u
LEFT JOIN orders o ON u.id = o.user_id AND YEAR(o.order_date) = 2024;

-- WHERE: Users without 2024 orders are REMOVED (effectively becomes INNER JOIN)
SELECT u.*, o.order_id
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE YEAR(o.order_date) = 2024;
```

🧠 **Rule of thumb:** If you want to **preserve the left side** and restrict the right side, put the condition in `ON`. If you want to hard-filter both sides, use `WHERE`.

### Sub-Pattern A — Comparing Rows Within Same Table

```sql
-- Employees earning more than their manager
SELECT e.name AS Employee
FROM Employee e
JOIN Employee m ON e.managerId = m.id
WHERE e.salary > m.salary;
```

### Sub-Pattern B — Finding Pairs

```sql
-- Find all pairs of students in the same class
SELECT a.name AS student1, b.name AS student2
FROM students a
JOIN students b ON a.class_id = b.class_id AND a.id < b.id;
```

### Sub-Pattern C — Non-Equi / Range Joins

🧠 *"Match each row to the bucket / band / tier it falls into."*

```sql
-- Look up each product's tax band by price
SELECT p.name, p.price, b.tax_rate
FROM products p
JOIN tax_bands b
    ON p.price >= b.min_price
   AND p.price <  b.max_price;

-- Match events to the time window they belong to
SELECT e.id, w.label
FROM events e
JOIN windows w
    ON e.ts >= w.starts_at
   AND e.ts <  w.ends_at;
```

⚠️ Range joins cannot use simple hash/equi-join plans — they fall back to nested-loop or merge. Ensure the range column is indexed on at least one side, and prefer half-open intervals (`>= min AND < max`) to avoid double-counting boundaries.

### 📝 Sample Problem — Trips and Users

> Tables `Trips(id, client_id, driver_id, status, request_date)`, `Users(users_id, banned, role)`. Find the cancellation rate for unbanned users between '2013-10-01' and '2013-10-03'.

```sql
SELECT
    t.request_date AS Day,
    ROUND(
        SUM(CASE WHEN t.status != 'completed' THEN 1 ELSE 0 END) / COUNT(*),
        2
    ) AS 'Cancellation Rate'
FROM Trips t
JOIN Users c ON t.client_id = c.users_id AND c.banned = 'No'
JOIN Users d ON t.driver_id = d.users_id AND d.banned = 'No'
WHERE t.request_date BETWEEN '2013-10-01' AND '2013-10-03'
GROUP BY t.request_date;
```

**Why ON for banned?** We filter banned users during the join so only trips with unbanned clients AND drivers remain.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Employees Earning More Than Managers | Easy | [▶ Practice](sql_sandbox.html?slug=employees-earning-more-than-managers) |
| 2 | Friend Requests II | Medium | [▶ Practice](sql_sandbox.html?slug=friend-requests-ii) |
| 3 | **Market Analysis I** | Medium | [▶ Practice](sql_sandbox.html?slug=market-analysis-i) |
| 4 | **Trips and Users** | Hard | [▶ Practice](sql_sandbox.html?slug=trips-and-users) |
| 5 | **Customers with Strictly Increasing Purchases** | Hard | [▶ Practice](sql_sandbox.html?slug=customers-with-strictly-increasing-purchases) |

---

## 2.4 Anti-Joins (Finding Non-Matches)

### What It Is

Find rows in table A that have **no corresponding row** in table B.

### Three Methods Compared

#### Method 1 — LEFT JOIN + IS NULL (Recommended)

```sql
SELECT a.*
FROM table_a a
LEFT JOIN table_b b ON a.key = b.key
WHERE b.key IS NULL;
```

🧠 "Join everything; keep only rows where the join failed (right side is NULL)."

#### Method 2 — NOT EXISTS

```sql
SELECT a.*
FROM table_a a
WHERE NOT EXISTS (
    SELECT 1 FROM table_b b WHERE b.key = a.key
);
```

🧠 "For each row in A, check: does a matching row exist in B? Keep only those where the answer is no."

⚙️ The subquery doesn't need to return data — `SELECT 1` is conventional. The engine short-circuits: it stops scanning B as soon as it finds one match.

#### Method 3 — NOT IN

```sql
SELECT a.*
FROM table_a a
WHERE a.key NOT IN (SELECT key FROM table_b WHERE key IS NOT NULL);
```

⚠️ **NULL trap:** If the subquery returns **any NULL**, `NOT IN` returns no rows at all (because `value NOT IN (..., NULL, ...)` is UNKNOWN). Always add `WHERE key IS NOT NULL` or use `NOT EXISTS`.

#### Method 4 — GROUP BY + HAVING COUNT(match) = 0

🧠 *"I need both the anti-join result and a group metric in one pass."*

```sql
-- Customers with 0 orders AND their signup month
SELECT
    c.id,
    c.name,
    DATE_FORMAT(c.signup_date, '%Y-%m') AS signup_month,
    COUNT(o.id) AS order_count          -- always 0
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.name, signup_month
HAVING COUNT(o.id) = 0;
```

💡 Useful when downstream logic also needs group-level aggregates; saves a second pass over the joined set.

### Performance Comparison

| Method | NULL-safe? | Performance | Readability |
|---|---|---|---|
| LEFT JOIN + IS NULL | ✅ | Good (optimized by most engines) | High |
| NOT EXISTS | ✅ | Often best (short-circuits) | Medium |
| NOT IN | ❌ (NULL trap) | Can be slow (materializes subquery) | High |
| GROUP BY + HAVING COUNT = 0 | ✅ | Extra aggregate cost | Medium — useful with aggregates |

💡 **General rule:** Use `NOT EXISTS` when performance matters, `LEFT JOIN + IS NULL` for readability, avoid `NOT IN` unless the column is NOT NULL.

### 📝 Sample Problem — Customers Who Never Order

> Tables: `Customers(id, name)`, `Orders(id, customerId)`. Find customers who never placed an order.

```sql
-- Method 1: LEFT JOIN
SELECT c.name AS Customers
FROM Customers c
LEFT JOIN Orders o ON c.id = o.customerId
WHERE o.id IS NULL;

-- Method 2: NOT EXISTS
SELECT name AS Customers
FROM Customers c
WHERE NOT EXISTS (
    SELECT 1 FROM Orders o WHERE o.customerId = c.id
);
```

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Customers Who Never Order | Easy | [▶ Practice](sql_sandbox.html?slug=customers-who-never-order) |
| 2 | Students and Examinations | Easy | [▶ Practice](sql_sandbox.html?slug=students-and-examinations) |
| 3 | Find the Missing IDs | Medium | [▶ Practice](sql_sandbox.html?slug=find-the-missing-ids) |
| 4 | **Sales by Day of the Week** | Hard | [▶ Practice](sql_sandbox.html?slug=sales-by-day-of-the-week) |

---

## 2.5 Semi-Joins (Positive Matching)

### What It Is

The **opposite of anti-joins** — find rows in table A that **do** have a match in table B, but without duplicating rows (unlike INNER JOIN, which can multiply rows).

🧠 *"Give me customers who have placed at least one order — but list each customer only once."*

### Three Methods

```sql
-- Method 1: EXISTS (recommended — guaranteed no duplicates)
SELECT c.*
FROM customers c
WHERE EXISTS (
    SELECT 1 FROM orders o WHERE o.customer_id = c.id
);

-- Method 2: IN
SELECT c.*
FROM customers c
WHERE c.id IN (SELECT customer_id FROM orders);

-- Method 3: INNER JOIN with DISTINCT (less efficient)
SELECT DISTINCT c.*
FROM customers c
JOIN orders o ON c.id = o.customer_id;
```

⚠️ **Why not just INNER JOIN?** If a customer has 5 orders, INNER JOIN returns that customer 5 times. `EXISTS` and `IN` return them once.

| Method | Duplicates? | NULL-safe? | Performance |
|---|---|---|---|
| `EXISTS` | No | ✅ | Best (short-circuits) |
| `IN` | No | ⚠️ NULLs in subquery can cause issues | Good |
| `JOIN + DISTINCT` | Removed by DISTINCT | ✅ | Worst (joins then deduplicates) |

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 2 | Customers Who Bought All Products | Medium | [▶ Practice](sql_sandbox.html?slug=customers-who-bought-all-products) |
| 3 | **Active Users** | Medium | [▶ Practice](sql_sandbox.html?slug=active-users) |

---

## 2.6 Additional JOIN Types

### CROSS JOIN (Cartesian Product)

🧠 *"Generate every combination of rows from two tables."*

```sql
-- All combinations of sizes and colors
SELECT s.size, c.color
FROM sizes s
CROSS JOIN colors c;

-- Practical use: pair every student with every exam for attendance tracking
SELECT s.student_id, e.exam_id
FROM students s
CROSS JOIN exams e;
```

**Use in interviews:** Often used with LEFT JOIN anti-pattern to find **missing combinations**:

```sql
-- Find which (student, exam) pairs have no result
SELECT s.student_id, e.exam_id
FROM students s
CROSS JOIN exams e
LEFT JOIN results r ON s.student_id = r.student_id AND e.exam_id = r.exam_id
WHERE r.id IS NULL;
```

### FULL OUTER JOIN

Returns all rows from **both** tables, with NULLs where no match exists.

```sql
SELECT
    COALESCE(a.id, b.id) AS id,
    a.value AS left_val,
    b.value AS right_val
FROM table_a a
FULL OUTER JOIN table_b b ON a.id = b.id;
```

⚠️ **MySQL does not support FULL OUTER JOIN.** Emulate with:

```sql
SELECT * FROM a LEFT JOIN b ON a.id = b.id
UNION
SELECT * FROM a RIGHT JOIN b ON a.id = b.id;
```

### LATERAL JOIN / CROSS APPLY

🧠 *"For each row of the left table, run a correlated subquery in the FROM clause."*

```sql
-- PostgreSQL: LATERAL
SELECT d.dept_name, top_earner.*
FROM departments d
CROSS JOIN LATERAL (
    SELECT name, salary
    FROM employees e
    WHERE e.dept_id = d.id
    ORDER BY salary DESC
    LIMIT 3
) AS top_earner;

-- SQL Server: CROSS APPLY (same concept)
SELECT d.dept_name, top_earner.*
FROM departments d
CROSS APPLY (
    SELECT TOP 3 name, salary
    FROM employees e
    WHERE e.dept_id = d.id
    ORDER BY salary DESC
) AS top_earner;
```

💡 LATERAL is like a correlated subquery but in the FROM clause — it can return multiple columns and rows.

### ⚠️ Exploding Joins — The Silent Killer

Two joins that are each 1:N can multiply your row count.

```sql
-- Orders table: 1 row per order
-- order_items: N rows per order
-- payments:    M rows per order (installments)
SELECT o.id, i.sku, p.amount
FROM orders o
JOIN order_items i ON i.order_id = o.id
JOIN payments    p ON p.order_id = o.id;
-- Result: N × M rows per order. SUM(p.amount) now over-counts.
```

🧠 **Detection:** run `SELECT COUNT(*) FROM orders` and `SELECT COUNT(*) FROM <joined query>` — if they don't line up the way you expect, you have an explosion.

**Fix:** pre-aggregate one side into a CTE before joining, or use a separate CTE per child and join aggregates:
```sql
WITH item_tot AS (SELECT order_id, SUM(qty) AS qty FROM order_items GROUP BY order_id),
     pay_tot  AS (SELECT order_id, SUM(amount) AS paid FROM payments GROUP BY order_id)
SELECT o.id, i.qty, p.paid
FROM orders o
LEFT JOIN item_tot i ON i.order_id = o.id
LEFT JOIN pay_tot  p ON p.order_id = o.id;
```

---

## 2.7 Set Operations (UNION, INTERSECT, EXCEPT)

| Operation | Returns |
|---|---|
| `UNION ALL` | All rows from both queries (with duplicates) |
| `UNION` | Distinct rows from both queries |
| `INTERSECT` | Rows in both queries |
| `EXCEPT` / `MINUS` | Rows in the first but not the second |

🧠 *"UNION ALL to stack results, EXCEPT for anti-join on full rows."*

⚠️ Both sides must have the same number of columns with compatible types. Columns are matched **positionally**, not by name — reordering a `SELECT` list above a `UNION ALL` silently misaligns the output.

💡 **Performance:** `UNION` runs a sort/hash-dedup step over the combined result; `UNION ALL` just concatenates. Prefer `UNION ALL` whenever duplicates are impossible (e.g., disjoint date ranges, mutually-exclusive filters).

---

## 2.8 EXISTS vs IN

| Feature | IN | EXISTS |
|---|---|---|
| Syntax | `WHERE col IN (subquery)` | `WHERE EXISTS (subquery)` |
| NULL behavior | Fails with NULLs in list | NULL-safe |
| Performance (small subquery) | Good | Good |
| Performance (large subquery, indexed) | EXISTS often wins | ✅ |
| Correlation | Usually uncorrelated | Always correlated |

🧠 **Guideline:**
- Checking **membership in a fixed set**: `IN`
- Checking **existence with complex conditions**: `EXISTS`

---

## 2.9 Table Value Constructors & Series Generation

### VALUES Clause as Inline Data

```sql
-- Use VALUES as a virtual table (PostgreSQL, SQL Server)
SELECT * FROM (VALUES (1, 'A'), (2, 'B'), (3, 'C')) AS t(id, code);

-- MySQL equivalent
SELECT 1 AS id, 'A' AS code
UNION ALL SELECT 2, 'B'
UNION ALL SELECT 3, 'C';
```

### generate_series (PostgreSQL)

```sql
-- Numbers 1 through 10
SELECT generate_series(1, 10) AS n;

-- Date range (every day in January 2024)
SELECT generate_series('2024-01-01'::date, '2024-01-31'::date, '1 day'::interval) AS dt;

-- Practical: fill date gaps without recursive CTE
SELECT d.dt::date, COALESCE(s.amount, 0) AS amount
FROM generate_series(
    (SELECT MIN(sale_date) FROM sales),
    (SELECT MAX(sale_date) FROM sales),
    '1 day'::interval
) AS d(dt)
LEFT JOIN sales s ON d.dt::date = s.sale_date;
```

💡 `generate_series` replaces recursive CTEs for sequence generation in PostgreSQL — simpler and faster.

⚠️ **MySQL has no `generate_series`.** For the portable fallback (recursive CTE that emits a number/date series) see §4.3 Sub-Pattern A.

---
---

# PHASE 3 — Window Functions & Advanced Aggregation

> *The key differentiator in SQL interviews. Master these to handle analytics questions.*

---

## 3.1 Window Functions: Ranking

### What It Is

Assign a positional number to each row **within a partition** based on an ordering, without collapsing rows.

### The Three Ranking Functions

| Function | Ties | Gaps | Example for values (90, 90, 80) |
|---|---|---|---|
| `ROW_NUMBER()` | Breaks ties arbitrarily | No gaps | 1, 2, 3 |
| `RANK()` | Same rank for ties | Gaps after ties | 1, 1, 3 |
| `DENSE_RANK()` | Same rank for ties | No gaps | 1, 1, 2 |

⚙️ **How PARTITION BY + ORDER BY work together:**

```
RANK() OVER (PARTITION BY department ORDER BY salary DESC)
```

1. **PARTITION BY department** — creates independent "buckets" per department; ranking resets in each.
2. **ORDER BY salary DESC** — within each bucket, rows are sorted and numbered.

🧠 **Choosing the right function:**

| Need | Use |
|---|---|
| Exactly one row per group (dedup) | `ROW_NUMBER()` |
| Top-N allowing ties (e.g., "top 3 salaries" where 2 people tie for 3rd) | `DENSE_RANK()` |
| Top-N with strict positional cut-off | `RANK()` |

### Sub-Pattern A — Top-N per Group

🧠 *"Find the top K items within each category."*

**Template:**
```sql
WITH ranked AS (
    SELECT *,
           DENSE_RANK() OVER (
               PARTITION BY group_col
               ORDER BY metric DESC
           ) AS rnk
    FROM table_name
)
SELECT * FROM ranked WHERE rnk <= K;
```

⚠️ Cannot put `WHERE rnk <= K` inside the same SELECT that defines `rnk` — window functions run in `SELECT`, but `WHERE` runs before `SELECT`.

### Sub-Pattern B — Deduplication

🧠 *"Keep only the latest / first record per entity."*

```sql
WITH deduped AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY user_id
               ORDER BY created_at DESC
           ) AS rn
    FROM events
)
SELECT * FROM deduped WHERE rn = 1;
```

💡 **Dialect-specific shortcuts** (same result, less boilerplate):

| Engine | Syntax |
|---|---|
| PostgreSQL | `SELECT DISTINCT ON (user_id) * FROM events ORDER BY user_id, created_at DESC;` |
| Snowflake / BigQuery / Databricks / Teradata | `SELECT * FROM events QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) = 1;` |
| MySQL / SQL Server | No shortcut — use the CTE form above. |

### Sub-Pattern C — Nth Value

🧠 *"Find the 2nd highest salary."*

```sql
-- Using DENSE_RANK (handles ties)
WITH ranked AS (
    SELECT salary,
           DENSE_RANK() OVER (ORDER BY salary DESC) AS rnk
    FROM employees
)
SELECT DISTINCT salary FROM ranked WHERE rnk = 2;
```

💡 Use `DENSE_RANK` not `RANK` if you want `N = 2` to mean "the second distinct value" rather than skipping a position.

**Alternative — `LIMIT` + `OFFSET` on distinct values:**
```sql
SELECT DISTINCT salary
FROM employees
ORDER BY salary DESC
LIMIT 1 OFFSET 1;         -- 2nd distinct salary
```

| Approach | Handles ties correctly | Returns NULL when no Nth value | Portable |
|---|---|---|---|
| `DENSE_RANK` | ✅ (all tied rows returned) | Need extra wrapper to force NULL | All engines |
| `LIMIT 1 OFFSET N-1` | ✅ via `DISTINCT` | Returns empty set, not NULL — wrap in subquery + `IFNULL` / `COALESCE` if interviewer wants NULL | `LIMIT` syntax engine-specific |

 ("Second Highest Salary") is the canonical trick-question here — the expected answer wraps the `LIMIT` form in a subquery so the missing case returns `NULL` instead of zero rows.

### 📝 Sample Problem — Department Top 3 Salaries

> Table: `Employee(id, name, salary, departmentId)`, `Department(id, name)`. Find employees whose salary is in the top 3 **unique** salaries of their department.

```sql
WITH ranked AS (
    SELECT
        d.name  AS Department,
        e.name  AS Employee,
        e.salary AS Salary,
        DENSE_RANK() OVER (
            PARTITION BY e.departmentId
            ORDER BY e.salary DESC
        ) AS rnk
    FROM Employee e
    JOIN Department d ON e.departmentId = d.id
)
SELECT Department, Employee, Salary
FROM ranked
WHERE rnk <= 3;
```

**Why DENSE_RANK?** "Top 3 unique salaries" — if two people earn 100k, they both rank 1, and rank 2 goes to the next distinct salary. `RANK()` would skip rank 2.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Second Highest Salary | Medium | [▶ Practice](sql_sandbox.html?slug=second-highest-salary) |
| 2 | Nth Highest Salary | Medium | [▶ Practice](sql_sandbox.html?slug=nth-highest-salary) |
| 3 | Rank Scores | Medium | [▶ Practice](sql_sandbox.html?slug=rank-scores) |
| 4 | **Department Top Three Salaries** | Hard | [▶ Practice](sql_sandbox.html?slug=department-top-three-salaries) |
| 5 | **Market Analysis II** | Hard | [▶ Practice](sql_sandbox.html?slug=market-analysis-ii) |

---

## 3.2 Window Functions: Analytics (LAG / LEAD)

### What It Is

Access a value from a **previous row** (`LAG`) or **next row** (`LEAD`) in the ordered partition, without a self-join.

### Technical Mechanics

```sql
LAG(column, offset, default)  OVER (PARTITION BY ... ORDER BY ...)
LEAD(column, offset, default) OVER (PARTITION BY ... ORDER BY ...)
```

| Parameter | Meaning | Default |
|---|---|---|
| `column` | The value to retrieve | — |
| `offset` | How many rows back/forward | 1 |
| `default` | Value if no such row exists (first/last rows) | NULL |

⚙️ The engine sorts the partition, then for each row looks `offset` positions back (LAG) or forward (LEAD) and returns that row's value.

### Related Functions

| Function | Returns |
|---|---|
| `FIRST_VALUE(col)` | First value in the window frame |
| `LAST_VALUE(col)` | Last value in the window frame (⚠️ needs explicit frame) |
| `NTH_VALUE(col, n)` | The nth value in the frame |

⚠️ **LAST_VALUE pitfall:** The default frame is `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, so `LAST_VALUE` just returns the current row. Fix:

```sql
LAST_VALUE(col) OVER (
    ORDER BY date
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

### IGNORE NULLS / RESPECT NULLS — The Carry-Forward Pattern

🧠 *"Fill forward the last known non-null value."*

Sparse time series (e.g. daily price snapshots with missing days) need **last-observation-carried-forward**. The clean form:

```sql
-- Oracle, Snowflake, BigQuery, Redshift
SELECT
    dt,
    LAG(price IGNORE NULLS) OVER (ORDER BY dt) AS last_known_price
FROM price_snapshots;
```

⚠️ **PostgreSQL < 16 and MySQL do not support `IGNORE NULLS`.** Emulate it by partitioning on a running count of non-nulls:

```sql
WITH tagged AS (
    SELECT dt, price,
           COUNT(price) OVER (ORDER BY dt) AS grp   -- increments only on non-null
    FROM price_snapshots
)
SELECT dt,
       MAX(price) OVER (PARTITION BY grp) AS last_known_price
FROM tagged;
```

💡 `RESPECT NULLS` is the default — only specify it when overriding an upstream setting. The carry-forward pattern is one of the most common real-world reporting tricks; interviewers at analytics-heavy shops ask for it by another name ("fill nulls", "LOCF").

### Sub-Pattern A — Row-over-Row Comparison

🧠 *"Compare each row to the previous/next one — growth, change detection."*

```sql
SELECT
    month,
    revenue,
    revenue - LAG(revenue) OVER (ORDER BY month) AS mom_change,
    ROUND(
        100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
        / LAG(revenue) OVER (ORDER BY month), 2
    ) AS mom_pct
FROM monthly_revenue;
```

### Sub-Pattern B — Detecting State Changes

🧠 *"The status changed from X to Y — when did it happen?"*

```sql
SELECT *
FROM (
    SELECT *,
           LAG(status) OVER (PARTITION BY user_id ORDER BY event_date) AS prev_status
    FROM user_events
) t
WHERE prev_status = 'free' AND status = 'premium';
```

### Sub-Pattern C — Consecutive-Row Conditions

🧠 *"Find 3+ consecutive rows meeting a condition."* (Overlaps with Gaps & Islands)

```sql
SELECT DISTINCT t1.num AS ConsecutiveNums
FROM (
    SELECT num,
           LAG(num)  OVER (ORDER BY id) AS prev_num,
           LEAD(num) OVER (ORDER BY id) AS next_num
    FROM Logs
) t1
WHERE t1.num = t1.prev_num AND t1.num = t1.next_num;
```

### 📝 Sample Problem — Rising Temperature

> Table `Weather(id, recordDate, temperature)`. Find all dates where the temperature was higher than the previous day.

```sql
SELECT id
FROM (
    SELECT id, temperature,
           LAG(temperature) OVER (ORDER BY recordDate) AS prev_temp,
           LAG(recordDate)  OVER (ORDER BY recordDate) AS prev_date,
           recordDate
    FROM Weather
) t
WHERE temperature > prev_temp
  AND DATEDIFF(recordDate, prev_date) = 1;   -- ensure truly consecutive days
```

**Why check DATEDIFF?** There might be missing dates; LAG gives the previous *row*, not the previous *day*.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Rising Temperature | Easy | [▶ Practice](sql_sandbox.html?slug=rising-temperature) |
| 2 | Consecutive Numbers | Medium | [▶ Practice](sql_sandbox.html?slug=consecutive-numbers) |
| 3 | Game Play Analysis III | Medium | [▶ Practice](sql_sandbox.html?slug=game-play-analysis-iii) |
| 4 | **Find Cumulative Salary of an Employee** | Hard | [▶ Practice](sql_sandbox.html?slug=find-cumulative-salary-of-an-employee) |
| 5 | **Number of Comments per Post** | Medium | [▶ Practice](sql_sandbox.html?slug=number-of-comments-per-post) |

---

## 3.3 Window Frames

### What It Is

Define **which rows** within a partition the aggregate/analytic function operates on. This is the `ROWS BETWEEN ... AND ...` clause.

### Frame Boundary Reference

```
ROWS BETWEEN <start> AND <end>
```

| Boundary | Meaning |
|---|---|
| `UNBOUNDED PRECEDING` | First row of the partition |
| `N PRECEDING` | N rows before current |
| `CURRENT ROW` | The current row |
| `N FOLLOWING` | N rows after current |
| `UNBOUNDED FOLLOWING` | Last row of the partition |

⚙️ **ROWS vs RANGE:**

| Mode | Operates on |
|---|---|
| `ROWS` | Physical row positions (predictable) |
| `RANGE` | Logical value ranges (groups ties together) |

⚠️ **Default frame** (when ORDER BY is specified): `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. This can silently group ties, causing unexpected results with `SUM`. Prefer explicit `ROWS`.

**Concrete tie-bug demo.** Two rows share `dt = '2024-01-02'`:

```
dt           amount
2024-01-01   10
2024-01-02   20
2024-01-02   30
2024-01-03   40
```

```sql
-- Default RANGE: both tied rows get the SAME running total
SUM(amount) OVER (ORDER BY dt)
-- → 10, 60, 60, 100     ← "60" repeats; the second '2024-01-02' row looks skipped

-- Explicit ROWS: running total increments per physical row
SUM(amount) OVER (ORDER BY dt ROWS UNBOUNDED PRECEDING)
-- → 10, 30, 60, 100     ← the intended behaviour
```

💡 **Rule:** if ties in the `ORDER BY` column are possible, always use `ROWS`.

### Sub-Pattern A — Running Total / Cumulative Sum

🧠 *"Keep a running tally as rows accumulate."*

```sql
SELECT
    date,
    amount,
    SUM(amount) OVER (
        ORDER BY date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM transactions;
```

### Sub-Pattern B — Moving / Rolling Average

🧠 *"Smooth out noise with a N-period rolling average."*

```sql
-- 7-day moving average
SELECT
    date,
    value,
    AVG(value) OVER (
        ORDER BY date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_avg_7d
FROM daily_metrics;
```

💡 `6 PRECEDING AND CURRENT ROW` = 7 rows total. For the first 6 rows, fewer rows are available — the average is computed over whatever exists.

### Sub-Pattern C — Cumulative Max / Min

```sql
SELECT
    date,
    price,
    MAX(price) OVER (
        ORDER BY date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS all_time_high
FROM stock_prices;
```

### 📝 Sample Problem — Last Person to Fit in the Bus

> Table `Queue(person_id, person_name, weight, turn)`. Bus limit = 1000 kg. Find the last person who can board.

```sql
WITH cumulative AS (
    SELECT *,
           SUM(weight) OVER (ORDER BY turn ROWS UNBOUNDED PRECEDING) AS total
    FROM Queue
)
SELECT person_name
FROM cumulative
WHERE total <= 1000
ORDER BY turn DESC
LIMIT 1;
```

**Intuition:** Running sum of weight ordered by turn. The last person whose cumulative weight ≤ 1000 is the answer.

### Sub-Pattern D — Rolling N-Day Distinct Counts

🧠 *"For every date, count distinct users active in the last N days."* Classic MAU/DAU
rolling window. **`COUNT(DISTINCT …) OVER (…)` is not portable** (unsupported in SQLite and
most engines) — the portable workaround is a correlated subquery on a date spine:

```sql
WITH dates AS (SELECT DISTINCT login_date FROM Logins)
SELECT d.login_date AS activity_date,
       (SELECT COUNT(DISTINCT l.user_id) FROM Logins l
        WHERE l.login_date BETWEEN date(d.login_date,'-6 day') AND d.login_date) AS rolling_7d_users
FROM dates d;
```

💡 Plain `COUNT(*) OVER (ORDER BY d RANGE BETWEEN '6 day' PRECEDING AND CURRENT ROW)` works
for totals, but **distinct** counts need the correlated subquery (or a self-join on the spine).

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Game Play Analysis III | Medium | [▶ Practice](sql_sandbox.html?slug=game-play-analysis-iii) |
| 2 | Last Person to Fit in the Bus | Medium | [▶ Practice](sql_sandbox.html?slug=last-person-to-fit-in-the-bus) |
| 3 | Account Balance | Medium | [▶ Practice](sql_sandbox.html?slug=account-balance) |
| 4 | Rolling 7-Day Active Users | Medium | [▶ Practice](sql_sandbox.html?slug=rolling-7-day-active-users) |
| 5 | **Median Given Frequency of Numbers** | Hard | [▶ Practice](sql_sandbox.html?slug=median-given-frequency-of-numbers) |

---

## 3.4 Additional Window Functions

### PERCENTILE_CONT / PERCENTILE_DISC — Quantiles Done Right

🧠 *"Find the median, the 90th percentile, any quantile — without constructing it by hand."*

| Function | Returns | Interpolation? |
|---|---|---|
| `PERCENTILE_CONT(p)` | The value at percentile `p`, interpolated between the two nearest rows | Yes (continuous) |
| `PERCENTILE_DISC(p)` | The value of the first row whose cumulative fraction ≥ `p` | No (discrete — picks an actual row) |

```sql
-- Median (50th percentile) + P90 salary
SELECT
    PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY salary) AS median,
    PERCENTILE_CONT(0.9)  WITHIN GROUP (ORDER BY salary) AS p90
FROM employees;

-- Per-department median (use as a window aggregate)
SELECT
    dept_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary)
        OVER (PARTITION BY dept_id) AS dept_median
FROM employees;
```

**Engine support:** PostgreSQL, SQL Server 2012+, Oracle, Snowflake, BigQuery (`APPROX_QUANTILES`). **MySQL has no built-in** — construct manually (see LC-style workaround: `ROW_NUMBER` + `COUNT(*) OVER ()` and average the two middle rows).

💡 Prefer `PERCENTILE_CONT` for continuous numeric distributions; `PERCENTILE_DISC` when you need an existing data point (e.g., picking a representative row).

### NTILE, PERCENT_RANK, CUME_DIST

| Function | Returns | Use Case |
|---|---|---|
| `NTILE(n)` | Divides partition into n roughly equal buckets (1 to n) | Quartiles, percentiles |
| `PERCENT_RANK()` | `(rank - 1) / (total_rows - 1)` — 0 to 1 | Relative position |
| `CUME_DIST()` | Fraction of rows ≤ current value — `(0, 1]` | Cumulative distribution |

```sql
-- Divide employees into 4 salary quartiles
SELECT name, salary,
       NTILE(4) OVER (ORDER BY salary) AS quartile
FROM employees;

-- Percentile rank
SELECT name, salary,
       ROUND(PERCENT_RANK() OVER (ORDER BY salary), 2) AS pct_rank
FROM employees;
-- Lowest salary = 0.00, highest = 1.00

-- Cumulative distribution
SELECT name, salary,
       ROUND(CUME_DIST() OVER (ORDER BY salary), 2) AS cume_dist
FROM employees;
-- What fraction of employees earn ≤ this salary?
```

### Multiple Window Definitions (WINDOW Clause)

```sql
-- Instead of repeating OVER (PARTITION BY dept ORDER BY salary DESC) everywhere:
SELECT
    name,
    ROW_NUMBER() OVER w AS rn,
    RANK()       OVER w AS rnk,
    SUM(salary)  OVER w AS running_sum
FROM employees
WINDOW w AS (PARTITION BY dept_id ORDER BY salary DESC);
```

💡 Reduces repetition and errors when multiple window functions share the same partition/order.

### Window Function Cannot Be Nested

```sql
-- ILLEGAL ❌
SELECT SUM(ROW_NUMBER() OVER (ORDER BY id)) FROM t;

-- Fix: use a CTE ✅
WITH numbered AS (
    SELECT ROW_NUMBER() OVER (ORDER BY id) AS rn FROM t
)
SELECT SUM(rn) FROM numbered;
```

### QUALIFY — Filter Directly on Window Results

🧠 *"I want to filter on a window function without a wrapping CTE."*

Standard SQL forbids `WHERE rn = 1` because window functions run in `SELECT`, after `WHERE`. The workaround is the CTE pattern above. **Snowflake, BigQuery, Databricks, Teradata, and H2** add a dedicated `QUALIFY` clause that runs *after* `SELECT`:

```sql
SELECT user_id, created_at, event
FROM events
QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) = 1;
```

💡 Worth knowing even if your day-to-day dialect lacks it — most modern cloud warehouses support it, and it collapses the classic "dedup-via-ROW_NUMBER=1" idiom to a single statement.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | **Median Employee Salary** | Hard | [▶ Practice](sql_sandbox.html?slug=median-employee-salary) |
| 2 | **Median Given Frequency of Numbers** | Hard | [▶ Practice](sql_sandbox.html?slug=median-given-frequency-of-numbers) |

---

## 3.5 GROUPING SETS, ROLLUP, CUBE

🧠 *"I need subtotals and grand totals without running separate queries."*

```sql
-- ROLLUP: hierarchical subtotals (rightmost to leftmost)
SELECT region, product, SUM(sales) AS total
FROM sales_data
GROUP BY ROLLUP(region, product);
-- Produces: (region, product), (region, NULL), (NULL, NULL) ← grand total

-- CUBE: all possible combinations
SELECT region, product, SUM(sales) AS total
FROM sales_data
GROUP BY CUBE(region, product);
-- Produces: (region, product), (region, NULL), (NULL, product), (NULL, NULL)

-- GROUPING SETS: specify exact combinations
SELECT region, product, SUM(sales) AS total
FROM sales_data
GROUP BY GROUPING SETS (
    (region, product),   -- detail
    (region),            -- subtotal by region
    ()                   -- grand total
);
```

### Distinguishing NULLs from Subtotals

The `GROUPING()` function returns 1 when the NULL is from a subtotal, 0 when it's a real NULL in data:

```sql
SELECT
    CASE WHEN GROUPING(region) = 1 THEN 'ALL REGIONS' ELSE region END AS region,
    CASE WHEN GROUPING(product) = 1 THEN 'ALL PRODUCTS' ELSE product END AS product,
    SUM(sales) AS total
FROM sales_data
GROUP BY ROLLUP(region, product);
```

💡 **`GROUPING_ID(cols…)`** packs multiple `GROUPING()` bits into a single integer (bitmask). Useful for `ORDER BY` to keep totals at the bottom, or for assigning a report-level label:
```sql
ORDER BY GROUPING_ID(region, product), region, product
-- 0 = detail, 1 = product-subtotal, 2 = region-subtotal, 3 = grand total
```

---
---

# PHASE 4 — Advanced Patterns

> *These appear in Hard-tier interview problems. They typically combine Phase 2 + Phase 3 techniques.*

---

## 4.1 Gaps & Islands

### What It Is

Identify **contiguous sequences** ("islands") and **breaks** ("gaps") in ordered data.

### When to Reach for It

- "Find the longest streak of consecutive logins"
- "Report contiguous date ranges with the same status"
- "Find missing IDs in a sequence"

### Intuition

🧠 **The Row-Difference Trick:**

Given a consecutive sequence (1, 2, 3, 5, 6, 8):

```
value: 1  2  3  5  6  8
rn:    1  2  3  4  5  6
diff:  0  0  0  1  1  2   ← value - rn
```

Rows with the **same difference** belong to the **same island**. GROUP BY this difference to find island boundaries.

**Why it works:** In a perfect consecutive run, value increases by 1 and so does row_number, so their difference stays constant. A gap bumps the value without bumping row_number, creating a new group.

### Method 1 — Row Difference

```sql
WITH islands AS (
    SELECT *,
           value - ROW_NUMBER() OVER (ORDER BY value) AS grp
    FROM sequence_table
)
SELECT
    MIN(value) AS island_start,
    MAX(value) AS island_end,
    COUNT(*)   AS island_length
FROM islands
GROUP BY grp;
```

### Method 2 — LAG Flag + Cumulative Sum

🧠 *More flexible — works for non-integer data and complex conditions.*

1. Compare each row to the previous one (LAG).
2. Flag rows where a "new island" starts (gap detected).
3. Cumulative SUM of flags assigns an island ID.

```sql
WITH flagged AS (
    SELECT *,
           CASE
               WHEN value - LAG(value) OVER (ORDER BY value) > 1
                    OR LAG(value) OVER (ORDER BY value) IS NULL
               THEN 1
               ELSE 0
           END AS new_island
    FROM sequence_table
),
grouped AS (
    SELECT *,
           SUM(new_island) OVER (ORDER BY value) AS island_id
    FROM flagged
)
SELECT
    island_id,
    MIN(value) AS island_start,
    MAX(value) AS island_end
FROM grouped
GROUP BY island_id;
```

### Row-Difference vs LAG-Flag — Which to Use?

| Situation | Prefer |
|---|---|
| Integer/date sequence with fixed step 1 | Row-difference (cleaner, one pass) |
| Non-integer domain (floats, arbitrary categories) | LAG-flag |
| "Same island if condition X holds between rows" (not just `+1`) | LAG-flag — put the condition in the `CASE WHEN` |
| Need to count islands globally | Either |
| Engine lacks window functions | Neither — fall back to self-join (rare now) |

### Sub-Pattern A — Consecutive Days / Dates

🧠 Same principle, but subtract a date-based row_number. Compute `rn` in a first CTE, then subtract days — this avoids engine-specific quirks around `INTERVAL` accepting a window expression inline.

```sql
-- Streak of consecutive login dates per user
WITH numbered AS (
    SELECT
        user_id,
        login_date,
        ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY login_date) AS rn
    FROM logins
),
islands AS (
    -- MySQL
    SELECT user_id, login_date,
           DATE_SUB(login_date, INTERVAL rn DAY) AS grp
    FROM numbered

    -- PostgreSQL:  login_date - (rn * INTERVAL '1 day')  AS grp
    -- SQL Server:  DATEADD(day, -rn, login_date)         AS grp
)
SELECT
    user_id,
    MIN(login_date) AS streak_start,
    MAX(login_date) AS streak_end,
    COUNT(*) AS streak_length
FROM islands
GROUP BY user_id, grp;
```

### Sub-Pattern B — Consecutive Rows with Same Value

```sql
WITH islands AS (
    SELECT *,
           ROW_NUMBER() OVER (ORDER BY id)
         - ROW_NUMBER() OVER (PARTITION BY status ORDER BY id) AS grp
    FROM events
)
SELECT status, MIN(id), MAX(id), COUNT(*) AS run_length
FROM islands
GROUP BY status, grp;
```

### Sub-Pattern C — Finding Gaps (the other half of "Gaps & Islands")

🧠 *"Report the ranges of missing values, not the present ones."*

```sql
-- Each row with a gap > 1 to the next row marks the start of a missing range
WITH edges AS (
    SELECT
        value                                       AS gap_start_prev,
        LEAD(value) OVER (ORDER BY value)           AS gap_end_next
    FROM sequence_table
)
SELECT
    gap_start_prev + 1  AS missing_from,
    gap_end_next  - 1  AS missing_to
FROM edges
WHERE gap_end_next - gap_start_prev > 1;
```

**Use case:** finding missing IDs, missing business days, missing sequence numbers in a receipt stream. Symmetrical to the islands case — an "island of absence" between every two adjacent present values.

### 📝 Sample Problem — Consecutive Numbers

> Table `Logs(id, num)`. Find all numbers that appear at least three times consecutively.

```sql
SELECT DISTINCT l.num AS ConsecutiveNums
FROM Logs l
JOIN Logs l2 ON l.id = l2.id - 1 AND l.num = l2.num
JOIN Logs l3 ON l.id = l3.id - 2 AND l.num = l3.num;
```

Alternative with LAG/LEAD:

```sql
SELECT DISTINCT num AS ConsecutiveNums
FROM (
    SELECT num,
           LAG(num)  OVER (ORDER BY id) AS prev,
           LEAD(num) OVER (ORDER BY id) AS next
    FROM Logs
) t
WHERE num = prev AND num = next;
```

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Consecutive Numbers | Medium | [▶ Practice](sql_sandbox.html?slug=consecutive-numbers) |
| 2 | Active Businesses | Medium | [▶ Practice](sql_sandbox.html?slug=active-businesses) |
| 3 | Active Users | Medium | [▶ Practice](sql_sandbox.html?slug=active-users) |
| 4 | **Consecutive Transactions** | Hard | [▶ Practice](sql_sandbox.html?slug=consecutive-transactions) |
| 5 | **Human Traffic of Stadium** | Hard | [▶ Practice](sql_sandbox.html?slug=human-traffic-of-stadium) |
| 6 | **Consecutive Transactions with Increasing Amounts** | Hard | [▶ Practice](sql_sandbox.html?slug=consecutive-transactions-with-increasing-amounts) |

---

## 4.2 Overlapping Intervals

### Detecting Overlaps

🧠 Two intervals `[s1, e1]` and `[s2, e2]` overlap when `s1 <= e2 AND s2 <= e1`:

```sql
-- Find all overlapping booking pairs
SELECT a.id, b.id
FROM bookings a
JOIN bookings b
    ON a.id < b.id                          -- avoid self-pair and duplicates
    AND a.start_date <= b.end_date
    AND b.start_date <= a.end_date;
```

### Merging Overlapping Intervals

🧠 This is a **Gaps & Islands** variant — one of the hardest common patterns.

**Algorithm:**
1. For each row, check if it starts after the max end-date seen so far. If yes, new group.
2. Cumulative MAX of end_date across the ordered set.

```sql
WITH ordered AS (
    SELECT *,
           MAX(end_date) OVER (
               ORDER BY start_date
               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
           ) AS prev_max_end
    FROM events
),
flagged AS (
    SELECT *,
           CASE WHEN start_date > prev_max_end OR prev_max_end IS NULL
                THEN 1 ELSE 0
           END AS new_group
    FROM ordered
),
grouped AS (
    SELECT *,
           SUM(new_group) OVER (ORDER BY start_date) AS grp
    FROM flagged
)
SELECT
    grp,
    MIN(start_date) AS merged_start,
    MAX(end_date)   AS merged_end
FROM grouped
GROUP BY grp;
```

💡 **Common follow-up — total covered duration.** Once intervals are merged, coverage is just the sum of the merged lengths:
```sql
SELECT SUM(DATEDIFF(merged_end, merged_start) + 1) AS covered_days
FROM (  /* merged result from query above */ ) m;
```
Interviewers frequently chain this on top of the merge: "Given these maintenance windows, how many distinct days was the service down?"

### 📝 Sample Problem — Merge Overlapping Events in Same Hall

> Table `HallEvents(hall_id, start_day, end_day)`. Merge overlapping events per hall.

```sql
WITH ordered AS (
    SELECT *,
           MAX(end_day) OVER (
               PARTITION BY hall_id
               ORDER BY start_day
               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
           ) AS prev_max_end
    FROM HallEvents
),
flagged AS (
    SELECT *,
           CASE WHEN start_day > prev_max_end OR prev_max_end IS NULL
                THEN 1 ELSE 0
           END AS new_group
    FROM ordered
),
grouped AS (
    SELECT *,
           SUM(new_group) OVER (
               PARTITION BY hall_id ORDER BY start_day
           ) AS grp
    FROM flagged
)
SELECT
    hall_id,
    MIN(start_day) AS start_day,
    MAX(end_day) AS end_day
FROM grouped
GROUP BY hall_id, grp;
```

### Sweep-Line — Max Concurrency

🧠 *"Given a table of intervals, find the peak number of overlapping intervals at any instant."*
Generalized "meeting rooms" in SQL. Split each interval into two timeline events (`+1` at start,
`-1` at end), sort, and take the running max.

```sql
WITH events AS (
  SELECT start_time AS t,  1 AS delta FROM Meetings
  UNION ALL
  SELECT end_time   AS t, -1 AS delta FROM Meetings
)
SELECT MAX(running) AS max_concurrent
FROM (
  SELECT SUM(delta) OVER (ORDER BY t, delta ASC ROWS UNBOUNDED PRECEDING) AS running
  FROM events
);
```

⚠️ **Half-open intervals** `[start, end)` are the usual convention: a meeting ending at the
same instant another starts does not overlap. Sort end events (`delta = -1`) **before** start
events (`delta = +1`) at ties → tie-break `delta ASC`.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | **Streamer Banned Accounts** | Medium | [▶ Practice](sql_sandbox.html?slug=leetflex-banned-accounts) |
| 2 | Max Concurrent Meetings | Hard | [▶ Practice](sql_sandbox.html?slug=max-concurrent-meetings) |

---

## 4.3 Recursive CTEs

### What It Is

A CTE that references **itself**, producing rows iteratively until a termination condition is met.

### When to Reach for It

| Sub-Pattern | Signal in the Problem |
|---|---|
| **Hierarchy traversal** | "Find all reports under a manager", org chart, folder tree |
| **Sequence generation** | "Generate all dates between X and Y", "generate numbers 1–N" |
| **Graph walking** | "Find all connected nodes", route finding |
| **Iterative accumulation** | "Distribute passengers across buses one-by-one" |

### Intuition — How to Think About It

🧠 Think of recursion as a **loop that produces rows**:

1. **Base case (Anchor):** What rows do I start with? (e.g., the CEO, date = start_date, number = 1)
2. **Recursive step:** Given the rows I have so far, what new rows can I produce? (e.g., find direct reports of each person I already have)
3. **Termination:** When do I stop? (e.g., no more children, date > end_date, number > N)

The engine executes anchor → produces rows → feeds them back into the recursive member → produces more rows → repeats until no new rows appear.

### Technical Mechanics

```sql
WITH RECURSIVE cte AS (
    -- ANCHOR: runs once, seeds the result
    SELECT col1, col2, 1 AS depth
    FROM table_name
    WHERE condition          -- e.g., manager_id IS NULL

    UNION ALL

    -- RECURSIVE MEMBER: runs repeatedly
    SELECT t.col1, t.col2, cte.depth + 1
    FROM table_name t
    JOIN cte ON t.parent_id = cte.id
    WHERE cte.depth < 10     -- termination guard
)
SELECT * FROM cte;
```

⚙️ **Execution model:**

| Iteration | Working table contains | Action |
|---|---|---|
| 0 | Anchor rows | Seed |
| 1 | Rows joined to iteration-0 rows | Append |
| 2 | Rows joined to iteration-1 rows | Append |
| … | … | … |
| N | Empty set | **Stop** |

⚠️ **Pitfall:** Forgetting termination → infinite loop. Always add a `WHERE depth < N` or rely on the data naturally exhausting.

⚠️ **UNION ALL vs UNION:** Use `UNION ALL` (required by most engines). `UNION` deduplicates each iteration (PostgreSQL allows it, MySQL does not).

💡 **Standard SQL `SEARCH` / `CYCLE` clauses** (PostgreSQL 14+, Db2, Oracle): bolt onto a recursive CTE to guarantee a traversal order and break cycles safely:
```sql
WITH RECURSIVE org AS (
    SELECT id, manager_id, name FROM employees WHERE manager_id IS NULL
    UNION ALL
    SELECT e.id, e.manager_id, e.name
    FROM employees e JOIN org ON e.manager_id = org.id
)
SEARCH DEPTH FIRST BY id SET ord
CYCLE id SET is_cycle USING cycle_path
SELECT * FROM org ORDER BY ord;
```
`CYCLE` stops the recursion the moment a previously-visited node reappears, so you don't need a hand-rolled depth guard for arbitrary graphs.

### Sub-Pattern A — Sequence Generation

🧠 *"I need a series of numbers or dates that don't exist in any table."*

```sql
-- Generate numbers 1 through 12
WITH RECURSIVE seq AS (
    SELECT 1 AS n
    UNION ALL
    SELECT n + 1 FROM seq WHERE n < 12
)
SELECT n FROM seq;
```

**Use case:** Generate all months of a year, then LEFT JOIN to actual data to fill gaps with 0.

### Sub-Pattern B — Hierarchy / Tree Traversal

🧠 *"The table has a self-referencing foreign key (parent_id). I need to walk up or down the tree."*

```sql
-- Find all employees reporting (directly or indirectly) to manager_id = 1
WITH RECURSIVE reports AS (
    SELECT id, name, manager_id, 1 AS level
    FROM employees
    WHERE manager_id = 1

    UNION ALL

    SELECT e.id, e.name, e.manager_id, r.level + 1
    FROM employees e
    JOIN reports r ON e.manager_id = r.id
)
SELECT * FROM reports;
```

💡 **Tip:** Track `level` or build a `path` string (`CONCAT(path, '/', name)`) for debugging and display.

### 📝 Sample Problem — Generate Missing Dates

> Given a table `sales(sale_date DATE, amount INT)` with sparse dates, produce a result with **every date** from the min to max sale_date, showing 0 for dates with no sales.

```sql
WITH RECURSIVE all_dates AS (
    SELECT MIN(sale_date) AS dt FROM sales
    UNION ALL
    SELECT DATE_ADD(dt, INTERVAL 1 DAY)
    FROM all_dates
    WHERE dt < (SELECT MAX(sale_date) FROM sales)
)
SELECT
    d.dt AS sale_date,
    COALESCE(s.amount, 0) AS amount
FROM all_dates d
LEFT JOIN sales s ON d.dt = s.sale_date
ORDER BY d.dt;
```

**Why recursion?** No calendar table exists; we manufacture the continuous date spine ourselves.

### Sub-Pattern C — Transitive Closure (Org Chart)

🧠 *"Given an employee table with a self-referencing `manager_id`, count every manager's
transitive reports (direct + indirect)."* A recursive CTE walks the hierarchy downward, then
an outer aggregation counts each walked edge.

```sql
WITH RECURSIVE reports(mgr, emp) AS (
  SELECT manager_id, id FROM Employees WHERE manager_id IS NOT NULL
  UNION ALL
  SELECT r.mgr, e.id FROM reports r JOIN Employees e ON e.manager_id = r.emp
)
SELECT mgr, COUNT(*) AS total_reports
FROM reports
GROUP BY mgr;
```

💡 Same template works for any parent-child graph: folder tree size, bill-of-materials
explosion, reply-thread depth — the recursion builds the transitive closure, the outer
`GROUP BY` summarizes it.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Process Tasks Using Servers | Medium | [▶ Practice](sql_sandbox.html?slug=process-tasks-using-servers) |
| 2 | Find the Missing IDs | Medium | [▶ Practice](sql_sandbox.html?slug=find-the-missing-ids) |
| 3 | Managers with At Least 5 Reports | Medium | [▶ Practice](sql_sandbox.html?slug=managers-with-at-least-5-reports) |
| 4 | **Find the Quiet Students in All Exams** | Hard | [▶ Practice](sql_sandbox.html?slug=find-the-quiet-students-in-all-exams) |
| 5 | **Hopper Company Queries I** | Hard | [▶ Practice](sql_sandbox.html?slug=hopper-company-queries-i) |
| 6 | **Hopper Company Queries II** | Hard | [▶ Practice](sql_sandbox.html?slug=hopper-company-queries-ii) |

---

## 4.4 Pivoting (Rows → Columns)

### What It Is

Transform **row values** into **column headers**. SQL doesn't have a built-in PIVOT in standard syntax (SQL Server does), so we use `CASE` + aggregation.

### Intuition

🧠 Think of it as a two-step process:

1. **GROUP BY** the row identifier (what you want as rows in the output).
2. **Spread** each category value into its own column using `CASE WHEN category = 'X' THEN value END`, wrapped in `MAX/MIN/SUM`.

**Why MAX/MIN works:** Within each group, exactly one row matches each `CASE WHEN`. `MAX` of one value and a bunch of NULLs returns that one value.

### Sub-Pattern A — Simple Pivot

```sql
SELECT
    student_id,
    MAX(CASE WHEN subject = 'Math'    THEN score END) AS Math,
    MAX(CASE WHEN subject = 'English' THEN score END) AS English,
    MAX(CASE WHEN subject = 'Science' THEN score END) AS Science
FROM scores
GROUP BY student_id;
```

### Sub-Pattern B — Pivot with Multiple Rows per Category

🧠 *"Each category has multiple values — I need to align them row-by-row across columns."*

**Technique:** Assign `ROW_NUMBER()` within each category, then GROUP BY that row number.

```sql
WITH ranked AS (
    SELECT name, continent,
           ROW_NUMBER() OVER (PARTITION BY continent ORDER BY name) AS rn
    FROM Student
)
SELECT
    MAX(CASE WHEN continent = 'America' THEN name END) AS America,
    MAX(CASE WHEN continent = 'Asia'    THEN name END) AS Asia,
    MAX(CASE WHEN continent = 'Europe'  THEN name END) AS Europe
FROM ranked
GROUP BY rn;
```

### Sub-Pattern C — Unpivoting (Columns → Rows)

The reverse: break columns into rows using `UNION ALL` or `CROSS JOIN LATERAL`.

```sql
-- Manual unpivot
SELECT id, 'Q1' AS quarter, q1 AS revenue FROM sales
UNION ALL
SELECT id, 'Q2', q2 FROM sales
UNION ALL
SELECT id, 'Q3', q3 FROM sales
UNION ALL
SELECT id, 'Q4', q4 FROM sales;
```

### Median Calculation

🧠 *"SQL has no built-in MEDIAN — construct it."* Full treatment lives in **§3.4 → PERCENTILE_CONT / PERCENTILE_DISC** (the idiomatic one-liner). Reach for the manual `ROW_NUMBER` + `COUNT(*) OVER ()` construction only on MySQL, which lacks `PERCENTILE_CONT`:

```sql
-- MySQL fallback — average the middle row(s)
WITH ordered AS (
    SELECT val,
           ROW_NUMBER() OVER (ORDER BY val) AS rn,
           COUNT(*)     OVER ()             AS cnt
    FROM numbers
)
SELECT AVG(val) AS median
FROM ordered
WHERE rn IN (FLOOR((cnt + 1) / 2.0), CEIL((cnt + 1) / 2.0));
```

### Dynamic Pivoting (Stored Procedures)

When the number of pivot columns is unknown at query-writing time:

```sql
-- MySQL: Build the pivot query dynamically
SET @sql = NULL;
SELECT GROUP_CONCAT(
    DISTINCT CONCAT(
        'MAX(CASE WHEN category = ''', category, ''' THEN value END) AS `', category, '`'
    )
) INTO @sql FROM data_table;

SET @sql = CONCAT('SELECT id, ', @sql, ' FROM data_table GROUP BY id');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
```

⚠️ Dynamic SQL in stored procedures only — standard queries need known columns at parse time.

### 📝 Sample Problem — Reformat Department Table

> Table `Department(id, revenue, month)`. Pivot so each month is a column.

```sql
SELECT
    id,
    SUM(CASE WHEN month = 'Jan' THEN revenue END) AS Jan_Revenue,
    SUM(CASE WHEN month = 'Feb' THEN revenue END) AS Feb_Revenue,
    SUM(CASE WHEN month = 'Mar' THEN revenue END) AS Mar_Revenue
    -- ... continue for all 12 months
FROM Department
GROUP BY id;
```

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Product Sales Analysis III | Medium | [▶ Practice](sql_sandbox.html?slug=product-sales-analysis-iii) |
| 2 | Rearrange Products Table | Easy | [▶ Practice](sql_sandbox.html?slug=rearrange-products-table) |
| 4 | **Students Report By Geography** | Hard | [▶ Practice](sql_sandbox.html?slug=students-report-by-geography) |
| 5 | **Dynamic Pivoting of a Table** | Hard | [▶ Practice](sql_sandbox.html?slug=dynamic-pivoting-of-a-table) |

---

## 4.5 Advanced Analytical Patterns

### Year-over-Year (YoY) Comparison

🧠 *"Compare this year's metrics to the same period last year."*

```sql
WITH monthly AS (
    SELECT
        YEAR(order_date)  AS yr,
        MONTH(order_date) AS mo,
        SUM(amount)       AS revenue
    FROM orders
    GROUP BY YEAR(order_date), MONTH(order_date)
)
SELECT
    c.yr, c.mo, c.revenue AS current_revenue,
    p.revenue AS prior_year_revenue,
    ROUND(100.0 * (c.revenue - p.revenue) / p.revenue, 2) AS yoy_pct
FROM monthly c
LEFT JOIN monthly p ON c.mo = p.mo AND c.yr = p.yr + 1;
```

### Running Percentage / Cumulative Share

🧠 *"What percentage of total revenue does this row contribute, cumulatively?"*

```sql
SELECT
    product,
    revenue,
    SUM(revenue) OVER (ORDER BY revenue DESC) AS cumulative_revenue,
    ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC)
          / SUM(revenue) OVER (), 2) AS cumulative_pct
FROM product_sales
ORDER BY revenue DESC;
```

💡 This is the **Pareto analysis** — find which products make up 80% of revenue.

### Sessionization (Grouping Events by Time Gaps)

🧠 *"Group user clickstream events into sessions — a new session starts after 30 minutes of inactivity."*

```sql
WITH with_gap AS (
    SELECT *,
           CASE
               WHEN TIMESTAMPDIFF(MINUTE,
                   LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time),
                   event_time
               ) > 30  -- 30-min gap threshold
               OR LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time) IS NULL
               THEN 1
               ELSE 0
           END AS new_session
    FROM events
),
with_session_id AS (
    SELECT *,
           SUM(new_session) OVER (PARTITION BY user_id ORDER BY event_time) AS session_id
    FROM with_gap
)
SELECT user_id, session_id,
       MIN(event_time) AS session_start,
       MAX(event_time) AS session_end,
       COUNT(*) AS event_count
FROM with_session_id
GROUP BY user_id, session_id;
```

### Carry-Forward Last-Known Value (LOCF)

🧠 *"For dates with no snapshot, use the last-seen value."*

One of the most common analytics patterns — the engine-aware syntax (`LAG … IGNORE NULLS`) and a portable MySQL/older-PostgreSQL fallback (running count of non-nulls used as a partition key) live in **§3.2 → IGNORE NULLS / RESPECT NULLS**. Use it whenever you see "fill gaps", "forward-fill", "last known price/status as of date X."

### As-Of Join / Slowly Changing Dimension Type-2 Lookup

🧠 *"Find the record that was effective on a given date."*

Classic when a dimension has `(effective_from, effective_to)` ranges (SCD Type 2) and you need "what was the price on this order date?":

```sql
SELECT
    o.id,
    o.order_date,
    o.product_id,
    p.price
FROM orders o
JOIN product_price_history p
    ON p.product_id = o.product_id
   AND p.effective_from <= o.order_date
   AND (p.effective_to  >  o.order_date OR p.effective_to IS NULL);
```

💡 **Open-ended current row:** history tables often leave `effective_to` as `NULL` for the row that is currently in effect — the `OR … IS NULL` branch above captures it.

💡 **Dialect shortcut:** kdb+, ClickHouse, and DuckDB have a dedicated `ASOF JOIN` operator; in mainstream SQL, use the range predicate above.

### Correlated Subquery → JOIN Rewrite

🧠 *"Correlated subqueries run per-row conceptually. Rewriting as a JOIN is often faster."*

```sql
-- SLOW: Correlated subquery (conceptually runs once per employee)
SELECT name, salary,
       (SELECT AVG(salary) FROM employees e2 WHERE e2.dept_id = e1.dept_id) AS dept_avg
FROM employees e1;

-- FAST: JOIN rewrite (single aggregation pass)
SELECT e.name, e.salary, d.dept_avg
FROM employees e
JOIN (
    SELECT dept_id, AVG(salary) AS dept_avg
    FROM employees
    GROUP BY dept_id
) d ON e.dept_id = d.dept_id;

-- ALSO FAST: Window function (single pass)
SELECT name, salary,
       AVG(salary) OVER (PARTITION BY dept_id) AS dept_avg
FROM employees;
```

💡 **When to rewrite:** If the correlated subquery is slow, convert to a GROUP BY subquery + JOIN, or use a window function.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | User Activity Sessions | Hard | [▶ Practice](sql_sandbox.html?slug=user-activity-sessions) |
| 2 | **Product Price at a Given Date** (SCD-2) | Medium | [▶ Practice](sql_sandbox.html?slug=product-price-at-a-given-date) |

---

## 4.6 Funnel Conversion

### What It Is

Given an ordered sequence of product steps (e.g. `view → add_to_cart → checkout → purchase`),
compute how many distinct users reach each step and the drop-off between adjacent steps.
Every growth / e-commerce analytics team ships one of these dashboards.

### The Pattern — Loose Funnel (per-step counts)

```sql
SELECT step,
       COUNT(DISTINCT user_id) AS users_reached
FROM FunnelEvents
GROUP BY step
ORDER BY CASE step WHEN 'view'        THEN 1
                   WHEN 'add_to_cart' THEN 2
                   WHEN 'checkout'    THEN 3
                   WHEN 'purchase'    THEN 4 END;
```

### The Pattern — Strict Funnel (must have done all prior steps)

🧠 A strict funnel only counts a user at step *k* if they previously completed steps *1…k−1*.
Compute each user's deepest reached step with a window, then aggregate:

```sql
WITH reached AS (
  SELECT user_id,
         MAX(CASE step WHEN 'view'        THEN 1
                       WHEN 'add_to_cart' THEN 2
                       WHEN 'checkout'    THEN 3
                       WHEN 'purchase'    THEN 4 END) AS max_step
  FROM FunnelEvents GROUP BY user_id
)
SELECT s.step,
       SUM(CASE WHEN r.max_step >= s.ord THEN 1 ELSE 0 END) AS users_reached
FROM (VALUES ('view',1),('add_to_cart',2),('checkout',3),('purchase',4)) AS s(step,ord)
CROSS JOIN reached r
GROUP BY s.step, s.ord
ORDER BY s.ord;
```

💡 **Drop-off ratios:** wrap either pattern in a CTE and divide each step's count by the
previous step's count: `LAG(users_reached) OVER (ORDER BY ord)`.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Funnel Conversion Rates | Medium | [▶ Practice](sql_sandbox.html?slug=funnel-conversion-rates) |

---

## 4.7 A/B Test Lift

### What It Is

Given an assignment table (`user_id → variant`) and a conversions table (`user_id`), compute
per-variant conversion rate and the **lift** of treatment over control. Every experimentation
team runs this query daily.

### The Pattern

```sql
WITH rates AS (
  SELECT a.variant,
         COUNT(*)                 AS users,
         COUNT(c.user_id)         AS converters,
         1.0 * COUNT(c.user_id) / COUNT(*) AS conversion_rate
  FROM Assignments a
  LEFT JOIN Conversions c ON c.user_id = a.user_id
  GROUP BY a.variant
)
SELECT variant, users, converters,
       ROUND(conversion_rate, 4) AS conversion_rate,
       ROUND(conversion_rate
             - (SELECT conversion_rate FROM rates WHERE variant = 'control'), 4) AS absolute_lift,
       ROUND(conversion_rate
             / (SELECT conversion_rate FROM rates WHERE variant = 'control') - 1, 4) AS relative_lift
FROM rates;
```

⚠️ **LEFT JOIN** is critical — users assigned to a variant who *didn't* convert must still
count toward the denominator. An INNER JOIN silently inflates every rate.

💡 **Statistical significance** is out of scope for pure SQL — compute `p̂`, `n`, then hand
off to a z-test / chi-squared in the BI layer. SQL gets you the rates; stats gets you the
confidence.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | A/B Test Lift | Medium | [▶ Practice](sql_sandbox.html?slug=ab-test-lift) |

---
---

# PHASE 5 — Data Type Manipulation

> *Date logic, string manipulation, and JSON queries show up everywhere. Learn the syntax once, apply it repeatedly.*

---

## 5.1 Date Functions

### What It Is

Extract, manipulate, and compare temporal data. Dates are central to cohort analysis, period-over-period comparisons, and time-series reporting.

### Function Reference (MySQL / PostgreSQL)

| Operation | MySQL | PostgreSQL |
|---|---|---|
| Current date | `CURDATE()` / `NOW()` | `CURRENT_DATE` / `NOW()` |
| Extract year | `YEAR(d)` | `EXTRACT(YEAR FROM d)` |
| Extract month | `MONTH(d)` | `EXTRACT(MONTH FROM d)` |
| Extract day of week | `DAYOFWEEK(d)` (1=Sun) | `EXTRACT(DOW FROM d)` (0=Sun) |
| Truncate to month | `DATE_FORMAT(d, '%Y-%m-01')` | `DATE_TRUNC('month', d)` |
| Add interval | `DATE_ADD(d, INTERVAL 7 DAY)` | `d + INTERVAL '7 days'` |
| Difference in days | `DATEDIFF(d1, d2)` | `d1 - d2` (returns integer) |
| Difference in minutes / hours / etc. | `TIMESTAMPDIFF(unit, d1, d2)` | `EXTRACT(EPOCH FROM (d2 - d1)) / 60` |
| Age between two dates | *(compute manually)* | `AGE(d2, d1)` → `INTERVAL` |
| Format | `DATE_FORMAT(d, '%Y-%m')` | `TO_CHAR(d, 'YYYY-MM')` |

### Sub-Pattern A — Period Grouping

🧠 *"Aggregate by week / month / quarter."*

```sql
-- Monthly revenue
SELECT
    DATE_FORMAT(order_date, '%Y-%m') AS month,
    SUM(amount) AS revenue
FROM orders
GROUP BY DATE_FORMAT(order_date, '%Y-%m')
ORDER BY month;
```

### Sub-Pattern B — Date Filtering with Ranges

🧠 *"Records in the last N days / between two dates."*

```sql
-- Last 30 days (inclusive)
WHERE order_date >= CURDATE() - INTERVAL 30 DAY

-- Specific month
WHERE order_date >= '2024-03-01' AND order_date < '2024-04-01'
```

⚠️ Avoid `MONTH(order_date) = 3` — it prevents index usage. Use range conditions.

### Sub-Pattern C — Day-of-Week Analysis

```sql
SELECT
    DAYNAME(order_date) AS day_name,
    COUNT(*) AS order_count
FROM orders
GROUP BY DAYOFWEEK(order_date), DAYNAME(order_date)
ORDER BY DAYOFWEEK(order_date);
```

### Sub-Pattern D — Cohort / Retention Analysis

🧠 *"Of users who signed up in month X, how many were active in month X+1?"*

```sql
WITH first_activity AS (
    SELECT user_id, MIN(activity_date) AS cohort_date
    FROM activity
    GROUP BY user_id
)
SELECT
    DATE_FORMAT(f.cohort_date, '%Y-%m') AS cohort_month,
    COUNT(DISTINCT a.user_id) AS retained
FROM first_activity f
JOIN activity a ON f.user_id = a.user_id
    AND a.activity_date BETWEEN f.cohort_date + INTERVAL 30 DAY
                             AND f.cohort_date + INTERVAL 60 DAY
GROUP BY cohort_month;
```

### Calendar Tables

🧠 *"When I need a continuous date spine, should I generate it on-the-fly or keep a table?"*

A **calendar table** is a persistent table with one row per date (plus optional columns: `is_weekend`, `is_holiday`, `fiscal_quarter`, `iso_week`). Every reporting system of non-trivial size has one.

| Approach | When to prefer |
|---|---|
| `generate_series` / recursive CTE | Ad-hoc queries, short ranges, prototyping |
| **Calendar table** | Production reporting, joins that repeat, business-day logic, fiscal calendars, holidays |

```sql
-- PostgreSQL: build a 30-year calendar once
CREATE TABLE calendar AS
SELECT dt::date AS dt,
       EXTRACT(dow FROM dt)  AS day_of_week,
       EXTRACT(dow FROM dt) IN (0, 6) AS is_weekend
FROM generate_series('2000-01-01'::date, '2030-12-31'::date, '1 day') dt;
```

### Time Zones

⚠️ `TIMESTAMP` vs `TIMESTAMPTZ` is the #1 production data-quality bug. Store in UTC, convert at display time.

```sql
-- PostgreSQL / SQL Server
SELECT ts AT TIME ZONE 'UTC' AT TIME ZONE 'America/Los_Angeles' AS local_ts FROM events;

-- MySQL
SELECT CONVERT_TZ(ts, '+00:00', 'America/Los_Angeles') AS local_ts FROM events;
```

💡 Period grouping (e.g., `DATE_TRUNC('day', ts)`) gives different results depending on the session time zone — always convert *before* truncating when local buckets matter.

### 📝 Sample Problem — Monthly Transactions

> Table `Transactions(id, country, state, amount, trans_date)`. For each month and country, find total transactions, total approved, total amount, and approved amount.

```sql
SELECT
    DATE_FORMAT(trans_date, '%Y-%m') AS month,
    country,
    COUNT(*)                                         AS trans_count,
    SUM(CASE WHEN state = 'approved' THEN 1 ELSE 0 END) AS approved_count,
    SUM(amount)                                      AS trans_total_amount,
    SUM(CASE WHEN state = 'approved' THEN amount ELSE 0 END) AS approved_total_amount
FROM Transactions
GROUP BY DATE_FORMAT(trans_date, '%Y-%m'), country;
```

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Rising Temperature | Easy | [▶ Practice](sql_sandbox.html?slug=rising-temperature) |
| 2 | Monthly Transactions I | Medium | [▶ Practice](sql_sandbox.html?slug=monthly-transactions-i) |
| 3 | Restaurant Growth | Medium | [▶ Practice](sql_sandbox.html?slug=restaurant-growth) |
| 4 | Cohort Retention Day N | Hard | [▶ Practice](sql_sandbox.html?slug=cohort-retention-day-n) |
| 5 | **Friday Purchases I** | Hard | [▶ Practice](sql_sandbox.html?slug=friday-purchases-i) |
| 6 | **New Users Daily Count** | Medium | [▶ Practice](sql_sandbox.html?slug=new-users-daily-count) |

---

## 5.2 String Aggregation (CONCAT / GROUP_CONCAT)

### What It Is

Combine string values — either column-level concatenation or aggregating multiple rows into one delimited string.

### Function Reference

| Function | Engine | Purpose |
|---|---|---|
| `CONCAT(a, b, c)` | All | Column-level merge |
| `CONCAT_WS(sep, a, b, c)` | MySQL | Concat With Separator (skips NULLs) |
| `GROUP_CONCAT(expr ORDER BY col SEPARATOR ',')` | MySQL | Row aggregation |
| `STRING_AGG(expr, sep ORDER BY col)` | PostgreSQL / SQL Server | Row aggregation |
| `LISTAGG(expr, sep) WITHIN GROUP (ORDER BY col)` | Oracle | Row aggregation |

⚙️ **GROUP_CONCAT internals:**

1. Gathers all non-NULL values in the group.
2. Optionally applies `DISTINCT`.
3. Sorts by `ORDER BY` clause.
4. Joins them with `SEPARATOR` (default: comma).
5. ⚠️ Result is truncated at `group_concat_max_len` (default 1024 bytes in MySQL). Increase with `SET group_concat_max_len = 100000;`.

**Engine parity on the truncation/overflow gotcha:**

| Engine | Behaviour on overflow |
|---|---|
| MySQL `GROUP_CONCAT` | Silent truncation at `group_concat_max_len` |
| PostgreSQL `STRING_AGG` | No limit (grows as needed; watch memory) |
| SQL Server `STRING_AGG` | Returns `NVARCHAR(MAX)`; no silent truncation, but 2 GB hard limit |
| Oracle `LISTAGG` | **Raises ORA-01489** at 4000 bytes unless you specify `ON OVERFLOW TRUNCATE` |

### Sub-Pattern A — Aggregate List per Group

```sql
SELECT
    department,
    GROUP_CONCAT(name ORDER BY name SEPARATOR ', ') AS employees
FROM employees
GROUP BY department;
-- Output: "Engineering" → "Alice, Bob, Charlie"
```

### Sub-Pattern B — Building Formatted Output

🧠 *"Construct a mathematical equation, CSV line, or custom string."*

```sql
-- Build equation string: +2X^2-3X^1+1X^0
SELECT GROUP_CONCAT(
    CONCAT(
        CASE WHEN coef > 0 THEN '+' ELSE '' END,
        coef, 'X^', power
    )
    ORDER BY power DESC
    SEPARATOR ''
) AS equation
FROM terms;
```

### 📝 Sample Problem — Group Sold Products by Date

> Table `Activities(sell_date, product)`. For each sell_date, list the number of distinct products and their names (sorted, comma-separated).

```sql
SELECT
    sell_date,
    COUNT(DISTINCT product) AS num_sold,
    GROUP_CONCAT(DISTINCT product ORDER BY product SEPARATOR ',') AS products
FROM Activities
GROUP BY sell_date
ORDER BY sell_date;
```

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Group Sold Products By The Date | Easy | [▶ Practice](sql_sandbox.html?slug=group-sold-products-by-the-date) |
| 2 | Invalid Tweets | Easy | [▶ Practice](sql_sandbox.html?slug=invalid-tweets) |
| 3 | Strong Friendship | Medium | [▶ Practice](sql_sandbox.html?slug=strong-friendship) |

---

## 5.3 String Functions Beyond CONCAT

### Essential String Functions

| Function | MySQL | PostgreSQL | Purpose |
|---|---|---|---|
| Substring | `SUBSTRING(s, pos, len)` | `SUBSTRING(s FROM pos FOR len)` | Extract part |
| Length | `LENGTH(s)` / `CHAR_LENGTH(s)` | `LENGTH(s)` | Character count |
| Trim | `TRIM(s)` / `LTRIM` / `RTRIM` | Same | Remove whitespace |
| Replace | `REPLACE(s, from, to)` | Same | Substitute substring |
| Upper/Lower | `UPPER(s)` / `LOWER(s)` | Same | Case conversion |
| Position | `LOCATE(sub, s)` | `POSITION(sub IN s)` | Find substring |
| Pad | `LPAD(s, len, pad)` / `RPAD` | Same | Left/right pad |
| Reverse | `REVERSE(s)` | Same | Reverse string |
| Left/Right | `LEFT(s, n)` / `RIGHT(s, n)` | Same | First/last N chars |

### Pattern Matching

```sql
-- LIKE: simple wildcards
WHERE name LIKE 'J%'       -- starts with J
WHERE name LIKE '%son'     -- ends with son
WHERE name LIKE '_o%'      -- second character is o
WHERE name LIKE '%\_%'     -- contains literal underscore (escaped)

-- REGEXP / RLIKE (MySQL) / ~ (PostgreSQL)
WHERE email REGEXP '^[a-zA-Z0-9]+@'           -- MySQL
WHERE email ~ '^[a-zA-Z0-9]+@'                -- PostgreSQL
WHERE email SIMILAR TO '[a-zA-Z0-9]+@%'       -- ANSI SQL
```

⚠️ **LIKE with leading `%`** (`WHERE col LIKE '%xyz'`) cannot use indexes — requires full table scan.

### Splitting a String Into Rows

🧠 *"The column stores `'tag1,tag2,tag3'` — turn each tag into its own row."*

```sql
-- PostgreSQL: STRING_TO_ARRAY + UNNEST
SELECT id, UNNEST(STRING_TO_ARRAY(tags, ',')) AS tag FROM posts;

-- PostgreSQL alt: single-field piece
SELECT SPLIT_PART(full_name, ' ', 1) AS first_name FROM users;

-- SQL Server 2017+
SELECT id, value AS tag
FROM posts
CROSS APPLY STRING_SPLIT(tags, ',');

-- MySQL 8+: JSON_TABLE trick (wrap CSV as a JSON array first)
SELECT p.id, jt.tag
FROM posts p,
     JSON_TABLE(
         CONCAT('["', REPLACE(p.tags, ',', '","'), '"]'),
         '$[*]' COLUMNS (tag VARCHAR(100) PATH '$')
     ) jt;
```

💡 This is the canonical "tags CSV → rows for a join" interview warm-up. Once you have rows, the rest is ordinary SQL.

### String Hygiene — Case Normalization & Validation

🧠 Warm-up staples: proper-case a name, validate an email, extract a domain. FAANG onsites
frequently open with one of these.

```sql
-- Proper-case a name (first letter upper, rest lower)
SELECT UPPER(SUBSTR(name,1,1)) || LOWER(SUBSTR(name,2)) AS name FROM Users;

-- Validate an email (SQLite-portable; no REGEXP — use LIKE + GLOB)
WHERE mail LIKE '%@leetcode.com'
  AND (SUBSTR(mail,1,1) BETWEEN 'a' AND 'z' OR SUBSTR(mail,1,1) BETWEEN 'A' AND 'Z')
  AND SUBSTR(mail, 1, length(mail)-length('@leetcode.com')) NOT GLOB '*[^A-Za-z0-9_.-]*';
```

⚠️ **Engine quirk:** SQLite has no native REGEXP — the `GLOB` negated character class above is
the portable escape hatch. MySQL/PostgreSQL can use `REGEXP` / `~` directly.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Fix Names in a Table | Easy | [▶ Practice](sql_sandbox.html?slug=fix-names-in-a-table) |
| 2 | Find Users With Valid E-Mails | Easy | [▶ Practice](sql_sandbox.html?slug=find-users-with-valid-emails) |

---

## 5.4 JSON & Array Functions

🧠 *"Modern SQL databases store semi-structured data as JSON. Knowing how to query it is essential."*

### Extracting JSON Values

```sql
-- PostgreSQL
SELECT
    data->>'name'           AS name,          -- text extraction
    data->'address'->>'city' AS city,          -- nested extraction
    (data->>'age')::int      AS age            -- extract & cast
FROM users;

-- MySQL
SELECT
    JSON_UNQUOTE(JSON_EXTRACT(data, '$.name'))  AS name,
    JSON_EXTRACT(data, '$.address.city')        AS city,
    CAST(JSON_EXTRACT(data, '$.age') AS UNSIGNED) AS age
FROM users;

-- SQL Server
SELECT
    JSON_VALUE(data, '$.name')         AS name,
    JSON_VALUE(data, '$.address.city') AS city
FROM users;
```

### Aggregating INTO JSON / Arrays

```sql
-- PostgreSQL: Build JSON array from rows
SELECT dept_id,
       JSON_AGG(name ORDER BY name)      AS names_json,
       ARRAY_AGG(name ORDER BY name)     AS names_array
FROM employees
GROUP BY dept_id;

-- MySQL: Build JSON array
SELECT dept_id,
       JSON_ARRAYAGG(name)  AS names_json
FROM employees
GROUP BY dept_id;
```

### Unnesting / Expanding JSON Arrays

```sql
-- PostgreSQL: Expand JSON array into rows
SELECT id, elem::text AS tag
FROM posts,
     JSONB_ARRAY_ELEMENTS(tags) AS elem;

-- MySQL 8.0+: JSON_TABLE
SELECT p.id, jt.tag
FROM posts p,
     JSON_TABLE(p.tags, '$[*]' COLUMNS (tag VARCHAR(50) PATH '$')) AS jt;
```

### ARRAY Operations (PostgreSQL)

```sql
-- Array contains
SELECT * FROM products WHERE tags @> ARRAY['sale'];

-- Array overlap (any common element)
SELECT * FROM products WHERE tags && ARRAY['sale', 'new'];

-- Unnest array to rows
SELECT id, UNNEST(tags) AS tag FROM products;

-- Aggregate back to array
SELECT id, ARRAY_AGG(DISTINCT tag ORDER BY tag) AS unique_tags
FROM (SELECT id, UNNEST(tags) AS tag FROM products) sub
GROUP BY id;
```

| Operation | PostgreSQL | MySQL 8+ | SQL Server |
|-----------|-----------|----------|------------|
| Extract text | `->>'key'` | `JSON_UNQUOTE(JSON_EXTRACT())` | `JSON_VALUE()` |
| Extract object | `->'key'` | `JSON_EXTRACT()` | `JSON_QUERY()` |
| Array agg | `JSON_AGG()` | `JSON_ARRAYAGG()` | `FOR JSON PATH` |
| Unnest array | `JSONB_ARRAY_ELEMENTS()` | `JSON_TABLE()` | `OPENJSON()` |
| Check key exists | `?` operator | `JSON_CONTAINS_PATH()` | `ISJSON()` |

⚠️ **JSON columns are NOT sargable** by default — wrap in functional indexes:
```sql
-- PostgreSQL GIN index on JSONB
CREATE INDEX idx_data_gin ON users USING GIN (data);

-- MySQL: virtual column + index
ALTER TABLE users ADD COLUMN name_v VARCHAR(100) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(data, '$.name'))) STORED;
CREATE INDEX idx_name_v ON users(name_v);
```

---
---

# PHASE 6 — Performance, DML & Server-Side Logic

> *Show you can write production-quality queries. These topics separate "I can write SQL" from "I can build systems."*

---

## 6.1 Sargability & Index-Aware Queries

**SARGable** = "Search ARGument ABLE" — the predicate can leverage an index.

🧠 **Rule:** If a function wraps the column, the index is bypassed.

| ❌ Non-SARGable (no index) | ✅ SARGable (uses index) |
|---|---|
| `WHERE YEAR(created_at) = 2024` | `WHERE created_at >= '2024-01-01' AND created_at < '2025-01-01'` |
| `WHERE LOWER(name) = 'john'` | `WHERE name = 'John'` (case-insensitive collation) |
| `WHERE salary + 100 > 5000` | `WHERE salary > 4900` |
| `WHERE SUBSTRING(code, 1, 3) = 'ABC'` | `WHERE code LIKE 'ABC%'` |
| `WHERE col * 2 = 10` | `WHERE col = 5` |
| `WHERE DATE(created_at) = '2024-01-15'` | `WHERE created_at >= '2024-01-15' AND created_at < '2024-01-16'` |

💡 **General principle:** Keep the column "naked" on one side of the comparison. Move all operations to the constant side.

### LIKE and Indexes

```sql
WHERE name LIKE 'John%'    -- ✅ index usable (prefix match)
WHERE name LIKE '%John%'   -- ❌ full scan (leading wildcard)
WHERE name LIKE '%John'    -- ❌ full scan (leading wildcard)
```

### OR and Indexes

```sql
-- ❌ OR can prevent index use
WHERE dept = 'Sales' OR dept = 'Engineering'

-- ✅ IN is optimized better by most engines
WHERE dept IN ('Sales', 'Engineering')
```

---

## 6.2 Indexes & EXPLAIN Plans

🧠 *"Indexes are the #1 performance lever. Understanding them separates junior from senior engineers."*

### Index Types

| Type | Best For | Example |
|------|----------|---------|
| **B-tree** (default) | Equality, range, ORDER BY, BETWEEN | `CREATE INDEX idx ON t(col);` |
| **Hash** | Equality only (no range) | PostgreSQL: `CREATE INDEX idx ON t USING HASH(col);` |
| **GIN** | Full-text search, JSONB containment, arrays | `CREATE INDEX idx ON t USING GIN(col);` |
| **GiST** | Geometric/spatial, range types, nearest-neighbor | `CREATE INDEX idx ON t USING GIST(col);` |
| **BRIN** | Very large tables with natural ordering (timestamps) | `CREATE INDEX idx ON t USING BRIN(created_at);` |
| **Partial / Filtered** | Indexing only a slice of rows (e.g., `status = 'active'`) | PG: `CREATE INDEX … WHERE status='active';` · SQL Server: `CREATE INDEX … WHERE status='active';` |
| **Expression / Functional** | Indexing a computed value (`LOWER(email)`, `JSON_VALUE(...)`) | PG: `CREATE INDEX ON users (LOWER(email));` · MySQL 8: generated column + B-tree · Oracle: function-based index |

### Composite (Multi-Column) Indexes

```sql
CREATE INDEX idx_dept_salary ON employees(dept_id, salary);
```

⚠️ **Leftmost prefix rule:** This index helps queries filtering on:
- `WHERE dept_id = 5` ✅
- `WHERE dept_id = 5 AND salary > 50000` ✅
- `WHERE salary > 50000` ❌ (cannot skip leading column)

### Covering Indexes (Index-Only Scans)

```sql
-- PostgreSQL: INCLUDE clause
CREATE INDEX idx_covering ON orders(customer_id) INCLUDE (order_date, total);

-- Query satisfied entirely from index — no table lookup
SELECT order_date, total FROM orders WHERE customer_id = 42;
```

### Reading EXPLAIN Output

```sql
-- PostgreSQL
EXPLAIN ANALYZE SELECT * FROM orders WHERE customer_id = 42;

-- MySQL
EXPLAIN SELECT * FROM orders WHERE customer_id = 42;
```

**Key things to look for in EXPLAIN:**

| Term | Meaning | Good/Bad |
|------|---------|----------|
| **Seq Scan / Full Table Scan** | Reads every row | 🔴 Bad for large tables |
| **Index Scan** | Uses index to find rows, then fetches from table | 🟢 Good |
| **Index Only Scan** | Answered entirely from index | 🟢 Best |
| **Bitmap Index Scan** | Uses index to build bitmap, then scans | 🟡 OK for many matches |
| **Nested Loop** | For each outer row, scan inner | 🟡 Good for small outer set |
| **Hash Join** | Build hash table, probe it | 🟢 Good for equi-joins |
| **Sort / Merge Join** | Sort both sides, merge | 🟢 Good for pre-sorted data |
| **actual time / rows** | Real execution stats | Use to find bottlenecks |

### Common Anti-Patterns That Kill Index Usage

```sql
-- ❌ Function on indexed column (not SARGable)
WHERE YEAR(created_at) = 2024
-- ✅ Range predicate
WHERE created_at >= '2024-01-01' AND created_at < '2025-01-01'

-- ❌ Implicit cast prevents index use
WHERE varchar_col = 123  -- engine casts every row
-- ✅ Match types
WHERE varchar_col = '123'

-- ❌ OR across different columns
WHERE col_a = 1 OR col_b = 2
-- ✅ UNION ALL (each branch can use its own index)
SELECT * FROM t WHERE col_a = 1
UNION ALL
SELECT * FROM t WHERE col_b = 2 AND col_a != 1  -- deduplicate if needed
```

### When NOT to Index

- Small tables (< few thousand rows) — sequential scan is faster
- Columns with very low cardinality (e.g., boolean) — index won't help
- Write-heavy tables where reads are rare — indexes slow down INSERT/UPDATE
- Already indexed via PRIMARY KEY or UNIQUE constraint

---

## 6.3 ORDER BY + LIMIT Traps

### Non-Deterministic Results

⚠️ If `ORDER BY` columns have **duplicate values**, `LIMIT` picks arbitrarily among ties. Different executions may return different rows.

```sql
-- DANGEROUS: multiple employees have salary = 50000
SELECT * FROM employees ORDER BY salary DESC LIMIT 5;
-- Which 5 of the tied rows are returned? Unpredictable!

-- FIX: add a tiebreaker
SELECT * FROM employees ORDER BY salary DESC, id ASC LIMIT 5;
```

### LIMIT Without ORDER BY

```sql
-- DANGEROUS: no guaranteed order — results are arbitrary
SELECT * FROM employees LIMIT 10;

-- The only valid use: checking if data exists
SELECT 1 FROM employees LIMIT 1;
```

### Top-N Without LIMIT (FETCH FIRST — ANSI SQL)

```sql
-- ANSI SQL (PostgreSQL, SQL Server, Oracle 12c+)
SELECT * FROM employees
ORDER BY salary DESC
FETCH FIRST 5 ROWS ONLY;

-- With ties
SELECT * FROM employees
ORDER BY salary DESC
FETCH FIRST 5 ROWS WITH TIES;  -- includes all rows tied for 5th place
```

### Pagination

```sql
-- OFFSET-based (simple but slow for deep pages)
SELECT * FROM products ORDER BY id LIMIT 20 OFFSET 40;  -- page 3

-- Keyset pagination (faster — uses index)
SELECT * FROM products
WHERE id > 60          -- last id from previous page
ORDER BY id
LIMIT 20;
```

💡 Keyset pagination avoids scanning and discarding OFFSET rows — O(1) vs O(N) per page.

⚠️ Keyset pagination requires a **strictly monotonic, unique** ordering key. If you sort by `created_at`, ties will make you skip or duplicate rows across pages — use a composite cursor `(created_at, id)` and the row-value comparison:
```sql
WHERE (created_at, id) > (:last_created_at, :last_id)
ORDER BY created_at, id
LIMIT 20;
```

---

## 6.4 DELETE & UPDATE Patterns

### DELETE with Subquery

```sql
-- Delete duplicate rows (keep lowest id)
DELETE FROM Person
WHERE id NOT IN (
    SELECT min_id FROM (
        SELECT MIN(id) AS min_id FROM Person GROUP BY email
    ) AS keep
);
```

⚠️ MySQL requires the extra derived table wrapper — you can't DELETE from the same table that's in a subquery directly.

### UPDATE with JOIN

```sql
-- MySQL: UPDATE with JOIN
UPDATE employees e
JOIN departments d ON e.dept_id = d.id
SET e.dept_name = d.name;

-- PostgreSQL: UPDATE ... FROM
UPDATE employees
SET dept_name = d.name
FROM departments d
WHERE employees.dept_id = d.id;
```

### UPSERT / MERGE

```sql
-- MySQL: INSERT ... ON DUPLICATE KEY UPDATE
INSERT INTO inventory (product_id, quantity)
VALUES (1, 50)
ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity);

-- PostgreSQL: INSERT ... ON CONFLICT
INSERT INTO inventory (product_id, quantity)
VALUES (1, 50)
ON CONFLICT (product_id)
DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity;

-- ANSI SQL / SQL Server / Oracle: MERGE
MERGE INTO target t
USING source s ON t.id = s.id
WHEN MATCHED THEN UPDATE SET t.val = s.val
WHEN NOT MATCHED THEN INSERT (id, val) VALUES (s.id, s.val);
```

### `RETURNING` / `OUTPUT` — Read What You Just Wrote

🧠 *"I want the inserted/updated rows back without a second query."*

```sql
-- PostgreSQL / MariaDB 10.5+
INSERT INTO orders (customer_id, total)
VALUES (42, 99.99)
RETURNING id, created_at;

UPDATE accounts SET balance = balance - 100 WHERE id = 1
RETURNING id, balance AS new_balance;

-- SQL Server
INSERT INTO orders (customer_id, total)
OUTPUT INSERTED.id, INSERTED.created_at
VALUES (42, 99.99);
```

💡 Saves a round-trip and eliminates race conditions between "INSERT then SELECT" (the row you inserted may be one of many concurrent inserts). Essential for auto-generated PKs.

### 🔗 Practice Problems

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | Delete Duplicate Emails (State After Dedup) | Easy | [▶ Practice](sql_sandbox.html?slug=delete-duplicate-emails) |

💡 The Atlas runner executes `SELECT`-only — the equivalent post-state query is
`SELECT id, email FROM Person p WHERE id = (SELECT MIN(id) FROM Person WHERE email = p.email)`.
In production, run the `DELETE` form shown above.

---

## 6.5 Transactions & Isolation Levels

🧠 *"Transactions group statements into atomic units. Isolation levels control what concurrent transactions can see."*

### ACID Properties

| Property | Meaning |
|----------|---------|
| **Atomicity** | All statements succeed or all are rolled back |
| **Consistency** | DB moves from one valid state to another |
| **Isolation** | Concurrent transactions don't interfere |
| **Durability** | Committed data survives crashes |

### Transaction Syntax

```sql
BEGIN;  -- or START TRANSACTION

UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;

-- If both succeed:
COMMIT;
-- If anything fails:
ROLLBACK;
```

### Savepoints (Partial Rollback)

```sql
BEGIN;
INSERT INTO orders VALUES (1, 'Widget', 10);
SAVEPOINT sp1;
INSERT INTO orders VALUES (2, 'Gadget', 20);
-- Oops, undo only the second insert
ROLLBACK TO sp1;
COMMIT;  -- Only order 1 is committed
```

### Isolation Levels & Phenomena

| Level | Dirty Read | Non-Repeatable Read | Phantom Read | Use Case |
|-------|-----------|-------------------|-------------|----------|
| **READ UNCOMMITTED** | Possible | Possible | Possible | Almost never used |
| **READ COMMITTED** | ❌ | Possible | Possible | PostgreSQL default |
| **REPEATABLE READ** | ❌ | ❌ | Possible (MySQL: ❌) | MySQL/InnoDB default |
| **SERIALIZABLE** | ❌ | ❌ | ❌ | Financial transactions |

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN;
-- All reads see a consistent snapshot; conflicts cause rollback
SELECT balance FROM accounts WHERE id = 1;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
COMMIT;
```

### Phenomena Explained

- **Dirty Read:** Reading uncommitted data from another transaction
- **Non-Repeatable Read:** Re-reading a row gives different values (another txn committed an UPDATE)
- **Phantom Read:** Re-running a query returns new rows (another txn committed an INSERT)

### SELECT FOR UPDATE (Row-Level Locking)

```sql
BEGIN;
-- Lock the row so no other transaction can modify it until COMMIT
SELECT * FROM inventory WHERE product_id = 42 FOR UPDATE;
-- Safe to update based on what we read
UPDATE inventory SET quantity = quantity - 1 WHERE product_id = 42;
COMMIT;
```

⚠️ **Deadlock risk:** If Transaction A locks row 1 then requests row 2, while Transaction B locks row 2 then requests row 1, both deadlock. Always lock rows in a **consistent order**.

### `SKIP LOCKED` / `NOWAIT` — Work-Queue Patterns

🧠 *"Multiple workers are pulling from the same job table — I don't want them to block each other."*

```sql
-- Each worker claims the next available job; skips rows other workers have locked
BEGIN;
SELECT * FROM jobs
WHERE status = 'pending'
ORDER BY created_at
LIMIT 1
FOR UPDATE SKIP LOCKED;         -- PostgreSQL, MySQL 8+, Oracle

UPDATE jobs SET status = 'running' WHERE id = :claimed_id;
COMMIT;
```

| Modifier | Behaviour when row is locked |
|---|---|
| *(default)* | Wait until the other transaction commits or rolls back |
| `NOWAIT` | Immediately raise an error |
| `SKIP LOCKED` | Silently skip the row, move to the next |

💡 `SKIP LOCKED` is the standard way to build a reliable SQL-backed job queue without an external message broker.

---

## 6.6 Temporary Tables, CTEs, and Views

### When to Use What

| Feature | Scope | Materialized? | Indexed? | Use Case |
|---|---|---|---|---|
| **CTE** | Single query | No (inlined in most engines) | No | Readability, multi-step logic |
| **Subquery** | Single query | No | No | One-off derived tables |
| **Temp Table** | Session | Yes (disk/memory) | Yes | Large intermediate results, multiple references |
| **View** | Permanent (schema object) | No (re-evaluated each time) | No | Reusable query abstraction, access control |
| **Materialized View** | Permanent | Yes (stored on disk) | Yes | Expensive queries cached, refreshed periodically |

### Temp Table Syntax

```sql
-- MySQL
CREATE TEMPORARY TABLE temp_results AS
SELECT user_id, SUM(amount) AS total
FROM orders
GROUP BY user_id;

-- Use it multiple times in the session
SELECT * FROM temp_results WHERE total > 1000;
SELECT AVG(total) FROM temp_results;

-- Automatically dropped at session end, or:
DROP TEMPORARY TABLE temp_results;
```

### Views

```sql
-- Create a reusable view
CREATE VIEW active_customers AS
SELECT c.id, c.name, COUNT(o.id) AS order_count
FROM customers c
JOIN orders o ON c.id = o.customer_id
WHERE o.order_date >= CURRENT_DATE - INTERVAL '1 year'
GROUP BY c.id, c.name;

-- Use like a table
SELECT * FROM active_customers WHERE order_count > 5;
```

💡 **Updatable views & `WITH CHECK OPTION`.** Simple views (single table, no aggregates/DISTINCT) are updatable in most engines — `INSERT`/`UPDATE` against the view rewrites to the underlying table. Add `WITH CHECK OPTION` to stop writes that would produce a row no longer visible through the view:
```sql
CREATE VIEW active_customers_v AS
SELECT * FROM customers WHERE is_active = TRUE
WITH CHECK OPTION;
-- UPDATE active_customers_v SET is_active = FALSE WHERE id = 1;  -- rejected
```

### Materialized Views (PostgreSQL)

```sql
CREATE MATERIALIZED VIEW monthly_stats AS
SELECT DATE_TRUNC('month', order_date) AS month, SUM(amount) AS revenue
FROM orders
GROUP BY 1;

-- Refresh when needed
REFRESH MATERIALIZED VIEW monthly_stats;
```

💡 **CTE performance nuance:** PostgreSQL 12+ inlines CTEs by default (like subqueries). Use `WITH cte AS MATERIALIZED (...)` to force materialization if the CTE result is reused multiple times.

---

## 6.7 Stored Procedures, Functions & Triggers

🧠 *"Server-side logic. Know what they are and when to use them — interviews rarely deep-dive but expect awareness."*

### User-Defined Functions (UDFs)

```sql
-- PostgreSQL
CREATE OR REPLACE FUNCTION full_name(first TEXT, last TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN first || ' ' || last;
END;
$$ LANGUAGE plpgsql;

SELECT full_name(first_name, last_name) FROM employees;

-- MySQL
CREATE FUNCTION full_name(first VARCHAR(50), last VARCHAR(50))
RETURNS VARCHAR(101)
DETERMINISTIC
BEGIN
    RETURN CONCAT(first, ' ', last);
END;
```

### Stored Procedures

```sql
-- PostgreSQL (PROCEDURE — no return value, can manage transactions)
CREATE OR REPLACE PROCEDURE transfer_funds(
    sender INT, receiver INT, amount NUMERIC
)
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE accounts SET balance = balance - amount WHERE id = sender;
    UPDATE accounts SET balance = balance + amount WHERE id = receiver;
    COMMIT;
END;
$$;

CALL transfer_funds(1, 2, 100.00);
```

### Triggers (Brief Overview)

```sql
-- PostgreSQL: Log salary changes automatically
CREATE OR REPLACE FUNCTION log_salary_change()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO salary_audit(emp_id, old_salary, new_salary, changed_at)
    VALUES (OLD.id, OLD.salary, NEW.salary, NOW());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_salary_audit
    AFTER UPDATE OF salary ON employees
    FOR EACH ROW
    EXECUTE FUNCTION log_salary_change();
```

| Concept | Function | Procedure | Trigger |
|---------|----------|-----------|---------|
| Returns value | Yes (RETURNS) | No (CALL) | Implicit (RETURN NEW/OLD) |
| Use in SELECT | Yes | No | No (fires automatically) |
| Transaction control | No | Yes | No (runs in caller's txn) |
| When to use | Computed columns, reusable logic | Multi-step operations | Auditing, enforcing business rules |

⚠️ **Scalar UDF performance trap.** A user-defined scalar function called inside a large `SELECT` is typically invoked per row, can hide index-unfriendly expressions, and often blocks parallelism. Mitigations:
- **SQL Server 2019+**: scalar-UDF inlining — works only when the UDF is deterministic and avoids certain constructs. Verify with `sys.sql_modules.is_inlineable`.
- **PostgreSQL**: declare `IMMUTABLE` or `STABLE` (never `VOLATILE` for pure computation) so the planner can cache / inline the call and so functional indexes are usable.
- **General rule:** if a UDF wraps a single expression, prefer the expression (or a generated column, §1.2) over the function.

---
---

# QUICK REFERENCE

---

## Pattern Selection Decision Tree

```
What does the problem ask for?
│
├─ "Top N per group"                    → §3.1 Ranking
├─ "Compare to previous/next row"       → §3.2 LAG/LEAD
├─ "Running total / moving average"     → §3.3 Window Frame
├─ "Percentile / distribution bucket"   → §3.4 NTILE / PERCENT_RANK / CUME_DIST
├─ "Rows → Columns"                     → §4.4 Pivot
├─ "Consecutive / streak / gaps"        → §4.1 Gaps & Islands
├─ "Overlapping time ranges"            → §4.2 Overlapping Intervals
├─ "Year-over-year / period comparison" → §4.5 YoY Comparison
├─ "Sessionize events by time gap"      → §4.5 Sessionization
├─ "Cumulative % / Pareto analysis"     → §4.5 Running Percentage
├─ "Group by time period"               → §5.1 Date Functions
├─ "Combine strings from rows"          → §5.2 String Agg
├─ "Query JSON / semi-structured data"  → §5.4 JSON & Array Functions
├─ "Compare rows in same table"         → §2.3 Self-Join
├─ "Multi-step transformation"          → §2.2 CTEs
├─ "Find rows WITHOUT a match"          → §2.4 Anti-Join
├─ "Find rows WITH a match (semi-join)" → §2.5 Semi-Join
├─ "Summary statistics with filter"     → §2.1 GROUP BY + HAVING
├─ "Hierarchy / tree / generate series" → §4.3 Recursive CTE
├─ "Generate number/date series"        → §2.9 generate_series / VALUES
├─ "Slow query / needs optimization"    → §6.1 Sargability + §6.2 EXPLAIN
├─ "Concurrent writes / race condition" → §6.5 Transactions & Isolation
└─ "Multiple patterns needed"           → Combine via CTEs (§2.2)
```

---

## Common Mistakes

| # | Mistake | Fix |
|---|---|---|
| 1 | Using `WHERE` to filter in LEFT JOIN | Move condition to `ON` clause |
| 2 | `NOT IN` with NULLs in subquery | Use `NOT EXISTS` or add `WHERE col IS NOT NULL` |
| 3 | `LAST_VALUE` returning current row | Add `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` |
| 4 | `AVG` hiding NULLs | Use `AVG(COALESCE(col, 0))` if NULLs = 0 |
| 5 | Window function in WHERE | Wrap in CTE/subquery, then filter |
| 6 | GROUP BY with non-aggregated columns | Add to GROUP BY or wrap in aggregate (MySQL ONLY_FULL_GROUP_BY) |
| 7 | `DISTINCT` inside `COUNT` with NULL | NULLs are excluded — intentional or bug? |
| 8 | Infinite recursive CTE | Add `WHERE depth < N` termination guard |
| 9 | `BETWEEN` with timestamps | Misses same-day timestamps — use half-open range. See §0.5 |
| 10 | `ORDER BY` + `LIMIT` without tiebreaker | Add a unique column to ORDER BY for deterministic results |
| 11 | Integer division truncation | `7/2 = 3` in PostgreSQL/SQL Server; cast to `DECIMAL` |
| 12 | `DISTINCT` applies to entire row | `SELECT DISTINCT a, b` deduplicates (a, b) pairs, not just a |
| 13 | `LIKE` with `%` prefix | Cannot use index; consider full-text search or reverse index |
| 14 | Implicit type conversion in WHERE | `WHERE varchar_col = 123` bypasses index; use `'123'` |
| 15 | Comparing dates with timestamps | `WHERE date_col = '2024-01-15'` misses times within that day; use range |
| 16 | `NULL` in `CASE WHEN` | `CASE col WHEN NULL` never matches; use `CASE WHEN col IS NULL` |
| 17 | `SUM()` of empty set | Returns NULL, not 0; wrap in `COALESCE(SUM(col), 0)` |
| 18 | Aggregate in WHERE | Illegal; use HAVING for aggregate conditions |
| 19 | `SELECT *` with JOIN | Duplicates join-key columns; list columns explicitly |
| 20 | JSON extract returns string, not number | Cast explicitly: `(data->>'age')::int` or `CAST(... AS INT)` |
| 21 | Missing composite index prefix | `INDEX(a, b)` won't help `WHERE b = 5`; leftmost prefix rule |
| 22 | `FOR UPDATE` in wrong order | Lock rows in consistent order across transactions to avoid deadlocks |
| 23 | Correlated subquery killing performance | Rewrite as JOIN + GROUP BY or window function |
| 24 | `FLOAT` for money/financial data | Use `DECIMAL(19,4)` — float has precision errors (`0.1 + 0.2 ≠ 0.3`) |
| 25 | Forgetting `COMMIT` / auto-commit off | Transaction stays open, blocking other writes; always COMMIT or ROLLBACK |
| 26 | Operator precedence in `WHERE` | `AND` binds tighter than `OR` — parenthesize mixed expressions. See §0.6 |
| 27 | `COUNT(NULL)` returns 0, not NULL | Subtle in outer-join contexts — `COUNT(o.id)` after LEFT JOIN counts matches, not rows |
| 28 | Default `RANGE` window frame on ties | Running totals collapse across tied ORDER BY values; always specify `ROWS`. See §3.3 |
| 29 | `AVG` on an INT column truncates | PostgreSQL/SQL Server: `AVG(int_col)` returns int — cast one side to `DECIMAL` / `NUMERIC` |
| 30 | `UNION ALL` column mismatch | Columns align **positionally**, not by name — reordering a SELECT list silently misaligns output |

---

## 🎯 Bonus: Special Techniques

Problems that showcase a single unusual technique worth internalising.

| # | Problem | Difficulty | Practice |
|---|---|---|---|
| 1 | **Median Given Frequency of Numbers** | Median via cumulative frequency | [▶ Practice](sql_sandbox.html?slug=median-given-frequency-of-numbers) |
| 2 | **Friends Recommendations** | Self-join + anti-join filtering | [▶ Practice](sql_sandbox.html?slug=leetcodify-friends-recommendations) |
| 3 | **Dynamic Pivoting of a Table** | Dynamic SQL + PIVOT | [▶ Practice](sql_sandbox.html?slug=dynamic-pivoting-of-a-table) |
| 5 | **Tree Node** | Recursive CTE + type classification | [▶ Practice](sql_sandbox.html?slug=tree-node) |
| 6 | **Product Price at a Given Date** | As-of / SCD Type-2 lookup (see §4.5) | [▶ Practice](sql_sandbox.html?slug=product-price-at-a-given-date) |
| 7 | **Streamer Banned Accounts** | Interval overlap on same account | [▶ Practice](sql_sandbox.html?slug=leetflex-banned-accounts) |
| 8 | **Friday Purchases I** | Weekday bucketing via `DAYOFWEEK` / `EXTRACT(DOW)` | [▶ Practice](sql_sandbox.html?slug=friday-purchases-i) |

---

## 📌 Study Order Recommendation

> **Phase A — Foundation Patterns (tackle first):**
> 1. Aggregation + GROUP BY + HAVING (§2.1)
> 2. Subqueries & CTEs (§2.2)
> 3. Self-Joins (§2.3)
> 4. Anti-Joins (§2.4)
>
> **Phase B — Window Functions:**
> 5. Ranking (§3.1)
> 6. LAG / LEAD (§3.2)
> 7. Window Frames (§3.3)
>
> **Phase C — Advanced:**
> 8. Gaps & Islands (§4.1)
> 9. Date Functions (§5.1)
> 10. CONCAT / GROUP_CONCAT (§5.2)
> 11. Pivoting (§4.4)
> 12. Recursive CTEs (§4.3)
>
> **Phase D — Must-Do Hard Problems (final boss):**
> 1. **Medians on grouped data** — odd/even handling via window + cumulative counts (§3.3)
> 2. **Pivot-and-rank report tables** — conditional aggregation over ranked buckets (§4.4 + §3.1)
> 3. **Human-traffic gaps & islands** — 3+ consecutive rows, id-vs-row-number trick (§4.1)
> 4. **Multi-CTE retention funnels** — Day-1 vs Day-N cohort math (§5.1 + §2.2)
> 5. **Running-total capacity constraints** — stop-when-threshold-hit with window sum (§3.3)
> 6. **Weighted department-vs-company comparisons** — dual aggregate with HAVING filter (§2.1)

---

*Based on patterns from [luuck25/sql](https://github.com/luuck25/sql/blob/main/patterns.md), expanded with intuition, technical details, and worked examples.*

