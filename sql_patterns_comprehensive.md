# SQL Interview Patterns — Comprehensive Study Guide

> A structured, progressive guide to mastering SQL for technical interviews. Study in order — each phase builds on the previous one.

---

## How to Use This Guide

**Study in phase order.** Each phase assumes you've internalized the ones before it.

| Phase | Topics | Goal |
|---|---|---|
| **Phase 0** | Execution order, NULLs, type casting, CASE, BETWEEN, DISTINCT | Build the mental model of how SQL thinks |
| **Phase 1** | Data types, constraints, normalization, engine differences | Understand the tables before querying them |
| **Phase 2** | GROUP BY, CTEs, JOINs, Anti-Joins, Semi-Joins, Set Ops | Write any standard query confidently |
| **Phase 3** | Ranking, LAG/LEAD, Window Frames, GROUPING SETS | Handle analytics and reporting problems |
| **Phase 4** | Gaps & Islands, Intervals, Recursion, Pivoting, YoY, Sessionization | Solve hard-tier interview problems |
| **Phase 5** | Date functions, String functions, JSON & Array functions | Manipulate all data types fluently |
| **Phase 6** | Indexes, EXPLAIN, Sargability, Transactions, DML, Stored Procs, Views | Write production-quality, performant SQL |
| **Reference** | Decision tree, 25 common mistakes | Quick lookup during practice |

### Symbols

| Symbol | Meaning |
|--------|---------|
| 🧠 | Intuition / how to think about the problem |
| ⚙️ | Technical detail / how the function works internally |
| 📝 | Worked sample problem |
| ⚠️ | Common pitfall |
| 💡 | Pro tip |

---
---

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
| Window QUALIFY | ❌ | ❌ | ❌ (BigQuery/Snowflake only) |

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

### 📝 Sample Problem — Duplicate Emails (LC 182)

> Table `Person(id, email)`. Find all duplicate emails.

```sql
SELECT email
FROM Person
GROUP BY email
HAVING COUNT(*) > 1;
```

**Why GROUP BY + HAVING?** GROUP BY collapses all rows with the same email; HAVING filters to only groups with more than one row.

### 🔗 Practice Problems

| # | Problem | Difficulty | Link | Interactive IDE |
|---|---------|------------|------|-------------|
| 1 | Duplicate Emails | Easy | [LC 182](https://leetcode.com/problems/duplicate-emails/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=duplicate-emails) |
| 2 | Classes More Than 5 Students | Easy | [LC 596](https://leetcode.com/problems/classes-more-than-5-students/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=classes-more-than-5-students) |
| 3 | Customers Who Bought All Products | Medium | [LC 1045 🔒](https://leetcode.com/problems/customers-who-bought-all-products/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=customers-who-bought-all-products) |
| 4 | Immediate Food Delivery II | Medium | [LC 1174 🔒](https://leetcode.com/problems/immediate-food-delivery-ii/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=immediate-food-delivery-ii) |
| 5 | **Average Salary: Departments vs Company** | Hard | [LC 615 🔒](https://leetcode.com/problems/average-salary-departments-vs-company/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=average-salary-departments-vs-company) |

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

### 📝 Sample Problem — Exchange Seats (LC 626)

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

| # | Problem | Difficulty | Link | Interactive IDE |
|---|---------|------------|------|-------------|
| 1 | Customers Who Never Order | Easy | [LC 183](https://leetcode.com/problems/customers-who-never-order/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=customers-who-never-order) |
| 2 | Department Highest Salary | Medium | [LC 184](https://leetcode.com/problems/department-highest-salary/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=department-highest-salary) |
| 3 | Exchange Seats | Medium | [LC 626](https://leetcode.com/problems/exchange-seats/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=exchange-seats) |
| 4 | **Median Employee Salary** | Hard | [LC 569 🔒](https://leetcode.com/problems/median-employee-salary/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=median-employee-salary) |
| 5 | **Game Play Analysis V** | Hard | [LC 1097 🔒](https://leetcode.com/problems/game-play-analysis-v/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=game-play-analysis-v) |

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

### 📝 Sample Problem — Trips and Users (LC 262)

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

| # | Problem | Difficulty | Link | Interactive IDE |
|---|---------|------------|------|-------------|
| 1 | Employees Earning More Than Managers | Easy | [LC 181](https://leetcode.com/problems/employees-earning-more-than-their-managers/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=employees-earning-more-than-managers) |
| 2 | Friend Requests II | Medium | [LC 602 🔒](https://leetcode.com/problems/friend-requests-ii-who-has-the-most-friends/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=friend-requests-ii) |
| 3 | **Market Analysis I** | Medium | [LC 1158 🔒](https://leetcode.com/problems/market-analysis-i/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=market-analysis-i) |
| 4 | **Trips and Users** | Hard | [LC 262](https://leetcode.com/problems/trips-and-users/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=trips-and-users) |
| 5 | **Customers with Strictly Increasing Purchases** | Hard | [LC 2474 🔒](https://leetcode.com/problems/customers-with-strictly-increasing-purchases/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=customers-with-strictly-increasing-purchases) |

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

### Performance Comparison

| Method | NULL-safe? | Performance | Readability |
|---|---|---|---|
| LEFT JOIN + IS NULL | ✅ | Good (optimized by most engines) | High |
| NOT EXISTS | ✅ | Often best (short-circuits) | Medium |
| NOT IN | ❌ (NULL trap) | Can be slow (materializes subquery) | High |

💡 **General rule:** Use `NOT EXISTS` when performance matters, `LEFT JOIN + IS NULL` for readability, avoid `NOT IN` unless the column is NOT NULL.

### 📝 Sample Problem — Customers Who Never Order (LC 183)

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

| # | Problem | Difficulty | Link | Interactive IDE |
|---|---------|------------|------|-------------|
| 1 | Customers Who Never Order | Easy | [LC 183](https://leetcode.com/problems/customers-who-never-order/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=customers-who-never-order) |
| 2 | Students and Examinations | Easy | [LC 1280](https://leetcode.com/problems/students-and-examinations/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=students-and-examinations) |
| 3 | Find the Missing IDs | Medium | [LC 1613 🔒](https://leetcode.com/problems/find-the-missing-ids/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=find-the-missing-ids) |
| 4 | **Sales by Day of the Week** | Hard | [LC 1479 🔒](https://leetcode.com/problems/sales-by-day-of-the-week/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=sales-by-day-of-the-week) |

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

---

## 2.7 Set Operations (UNION, INTERSECT, EXCEPT)

| Operation | Returns |
|---|---|
| `UNION ALL` | All rows from both queries (with duplicates) |
| `UNION` | Distinct rows from both queries |
| `INTERSECT` | Rows in both queries |
| `EXCEPT` / `MINUS` | Rows in the first but not the second |

🧠 *"UNION ALL to stack results, EXCEPT for anti-join on full rows."*

⚠️ Both sides must have the same number of columns with compatible types.

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

### 📝 Sample Problem — Department Top 3 Salaries (LC 185)

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

| # | Problem | Difficulty | Link | Interactive IDE |
|---|---------|------------|------|-------------|
| 1 | Second Highest Salary | Medium | [LC 176](https://leetcode.com/problems/second-highest-salary/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=second-highest-salary) |
| 2 | Nth Highest Salary | Medium | [LC 177](https://leetcode.com/problems/nth-highest-salary/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=nth-highest-salary) |
| 3 | Rank Scores | Medium | [LC 178](https://leetcode.com/problems/rank-scores/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=rank-scores) |
| 4 | **Department Top Three Salaries** | Hard | [LC 185](https://leetcode.com/problems/department-top-three-salaries/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=department-top-three-salaries) |
| 5 | **Market Analysis II** | Hard | [LC 1159 🔒](https://leetcode.com/problems/market-analysis-ii/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=market-analysis-ii) |

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

### 📝 Sample Problem — Rising Temperature (LC 197)

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

| # | Problem | Difficulty | Link | Interactive IDE |
|---|---------|------------|------|-------------|
| 1 | Rising Temperature | Easy | [LC 197](https://leetcode.com/problems/rising-temperature/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=rising-temperature) |
| 2 | Consecutive Numbers | Medium | [LC 180](https://leetcode.com/problems/consecutive-numbers/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=consecutive-numbers) |
| 3 | **Find Cumulative Salary of an Employee** | Hard | [LC 579 🔒](https://leetcode.com/problems/find-cumulative-salary-of-an-employee/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=find-cumulative-salary-of-an-employee) |

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

### 📝 Sample Problem — Last Person to Fit in the Bus (LC 1204)

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

### 🔗 Practice Problems

| # | Problem | Difficulty | Link | Interactive IDE |
|---|---------|------------|------|-------------|
| 1 | Game Play Analysis III | Medium | [LC 550 🔒](https://leetcode.com/problems/game-play-analysis-iii/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=game-play-analysis-iii) |
| 2 | Last Person to Fit in the Bus | Medium | [LC 1204](https://leetcode.com/problems/last-person-to-fit-in-the-bus/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=last-person-to-fit-in-the-bus) |
| 3 | Account Balance | Medium | [LC 2010 🔒](https://leetcode.com/problems/account-balance/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=account-balance) |
| 4 | **Median Given Frequency of Numbers** | Hard | [LC 571 🔒](https://leetcode.com/problems/median-given-frequency-of-numbers/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=median-given-frequency-of-numbers) |

---

## 3.4 Additional Window Functions

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

### Sub-Pattern A — Consecutive Days / Dates

🧠 Same principle, but subtract a date-based row_number:

```sql
-- Streak of consecutive login dates per user
WITH islands AS (
    SELECT
        user_id,
        login_date,
        login_date - INTERVAL ROW_NUMBER() OVER (
            PARTITION BY user_id ORDER BY login_date
        ) DAY AS grp
    FROM logins
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

### 📝 Sample Problem — Consecutive Numbers (LC 180)

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

| # | Problem | Difficulty | Link | Interactive IDE |
|---|---------|------------|------|-------------|
| 1 | Consecutive Numbers | Medium | [LC 180](https://leetcode.com/problems/consecutive-numbers/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=consecutive-numbers) |
| 2 | Active Businesses | Medium | [LC 1225 🔒](https://leetcode.com/problems/active-businesses/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=active-businesses) |
| 3 | Active Users | Medium | [LC 1285 🔒](https://leetcode.com/problems/active-users/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=active-users) |
| 4 | **Human Traffic of Stadium** | Hard | [LC 601](https://leetcode.com/problems/human-traffic-of-stadium/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=human-traffic-of-stadium) |
| 5 | **Consecutive Transactions with Increasing Amounts** | Hard | [LC 2701 🔒](https://leetcode.com/problems/consecutive-transactions-with-increasing-amounts/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=consecutive-transactions-with-increasing-amounts) |

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

### 📝 Sample Problem — Merge Overlapping Events in Same Hall (LC 2494)

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

### 🔗 Practice Problems

| # | Problem | Difficulty | Link | Interactive IDE |
|---|---------|------------|------|-------------|
| 1 | Process Tasks Using Servers | Medium | [LC 1270 🔒](https://leetcode.com/problems/process-tasks-using-servers/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=process-tasks-using-servers) |
| 2 | Find the Missing IDs | Medium | [LC 1613 🔒](https://leetcode.com/problems/find-the-missing-ids/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=find-the-missing-ids) |
| 3 | **Find the Quiet Students in All Exams** | Hard | [LC 1336](https://leetcode.com/problems/find-the-quiet-students-in-all-exams/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=find-the-quiet-students-in-all-exams) |
| 4 | **Hopper Company Queries I** | Hard | [LC 1635 🔒](https://leetcode.com/problems/hopper-company-queries-i/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=hopper-company-queries-i) |
| 5 | **Hopper Company Queries II** | Hard | [LC 1645 🔒](https://leetcode.com/problems/hopper-company-queries-ii/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=hopper-company-queries-ii) |

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

🧠 *"SQL has no built-in MEDIAN — construct it."*

**Method 1: ROW_NUMBER approach**
```sql
WITH ordered AS (
    SELECT val,
           ROW_NUMBER() OVER (ORDER BY val) AS rn,
           COUNT(*) OVER () AS cnt
    FROM numbers
)
SELECT AVG(val) AS median
FROM ordered
WHERE rn IN (FLOOR((cnt + 1) / 2.0), CEIL((cnt + 1) / 2.0));
```

**Method 2: PERCENTILE_CONT (PostgreSQL / SQL Server)**
```sql
SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY val) AS median
FROM numbers;
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

### 📝 Sample Problem — Reformat Department Table (LC 1179)

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

| # | Problem | Difficulty | Link | Interactive IDE |
|---|---------|------------|------|-------------|
| 1 | Product Sales Analysis III | Medium | [LC 1179 🔒](https://leetcode.com/problems/product-sales-analysis-iii/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=product-sales-analysis-iii) |
| 2 | Rearrange Products Table | Easy | [LC 2991](https://leetcode.com/problems/rearrange-products-table/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=rearrange-products-table) |
| 3 | **Students Report By Geography** | Hard | [LC 618 🔒](https://leetcode.com/problems/students-report-by-geography/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=students-report-by-geography) |

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

### 📝 Sample Problem — Monthly Transactions (LC 1193)

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

| # | Problem | Difficulty | Link | Interactive IDE |
|---|---------|------------|------|-------------|
| 1 | Rising Temperature | Easy | [LC 197](https://leetcode.com/problems/rising-temperature/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=rising-temperature) |
| 2 | Monthly Transactions I | Medium | [LC 1193 🔒](https://leetcode.com/problems/monthly-transactions-i/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=monthly-transactions-i) |
| 3 | Restaurant Growth | Medium | [LC 1454 🔒](https://leetcode.com/problems/restaurant-growth/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=restaurant-growth) |

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

### 📝 Sample Problem — Group Sold Products by Date (LC 1484)

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

| # | Problem | Difficulty | Link | Interactive IDE |
|---|---------|------------|------|-------------|
| 1 | Group Sold Products By The Date | Easy | [LC 1484 🔒](https://leetcode.com/problems/group-sold-products-by-the-date/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=group-sold-products-by-the-date) |
| 2 | Invalid Tweets | Easy | [LC 2118](https://leetcode.com/problems/invalid-tweets/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=invalid-tweets) |
| 3 | Strong Friendship | Medium | [LC 2199 🔒](https://leetcode.com/problems/strong-friendship/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=strong-friendship) |

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
| 9 | `BETWEEN` with timestamps | `BETWEEN '2024-01-01' AND '2024-01-31'` misses times; use `< '2024-02-01'` |
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

---

## 🎯 Bonus: Special Techniques

| # | Problem | Pattern | Link | Free Practice |
|---|---------|---------|------|-------------|
| 1 | **Median Given Frequency of Numbers** | Median calculation with cumulative sums | [LC 571 🔒](https://leetcode.com/problems/median-given-frequency-of-numbers/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=median-given-frequency-of-numbers) |
| 2 | **Leetcodify Friends Recommendations** | Self-join + anti-join filtering | [LC 1917 🔒](https://leetcode.com/problems/leetcodify-friends-recommendations/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=leetcodify-friends-recommendations) |
| 3 | **Dynamic Pivoting of a Table** | Dynamic SQL + PIVOT | [LC 2252 🔒](https://leetcode.com/problems/dynamic-pivoting-of-a-table/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=dynamic-pivoting-of-a-table) |
| 4 | **Build a Matrix With Conditions** | Matrix construction with CTE + CASE | [LC 2253 🔒](https://leetcode.com/problems/build-a-matrix-with-conditions/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=build-a-matrix-with-conditions) |
| 5 | **Average Selling Price** | Medium / Removed from sections | [LC 1369 🔒](https://leetcode.com/problems/average-selling-price/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=average-selling-price) |
| 6 | **Number of Comments per Post** | Easy / Removed from sections | [LC 1412 🔒](https://leetcode.com/problems/number-of-comments-per-post/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=number-of-comments-per-post) |
| 7 | **New Users Daily Count** | Medium / Removed from sections | [LC 1972 🔒](https://leetcode.com/problems/new-users-daily-count/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=new-users-daily-count) |
| 8 | **Steps to Make Array Non-decreasing** | Medium / Removed from sections | [LC 2362 🔒](https://leetcode.com/problems/steps-to-make-array-non-decreasing/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=steps-to-make-array-non-decreasing) |
| 9 | **Number of Unique Categories** | Medium / Removed from sections | [LC 2720 🔒](https://leetcode.com/problems/number-of-unique-categories/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=number-of-unique-categories) |
| 10 | **Count the Number of Good Partitions** | Hard / Removed from sections | [LC 2793 🔒](https://leetcode.com/problems/count-the-number-of-good-partitions/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=count-the-number-of-good-partitions) |
| 11 | **Count of Interesting Subarrays** | Medium / Removed from sections | [LC 2995 🔒](https://leetcode.com/problems/count-of-interesting-subarrays/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=count-of-interesting-subarrays) |
| 12 | Tree Node | Medium / Removed from sections | [LC 608](https://leetcode.com/problems/tree-node/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=tree-node) |
| 13 | **Count Salary Categories** | Medium / Removed from sections | [LC 2993 🔒](https://leetcode.com/problems/count-salary-categories/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=count-salary-categories) |
| 14 | **Longest Subsequence With Limited Sum** | Medium / Removed from sections | [LC 2173](https://leetcode.com/problems/longest-subsequence-with-limited-sum/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=longest-subsequence-with-limited-sum) |
| 15 | **Consecutive Transactions** | Medium / Removed from sections | [LC 2752 🔒](https://leetcode.com/problems/consecutive-transactions/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=consecutive-transactions) |
| 16 | **Leetflex Banned Accounts** | Medium / Removed from sections | [LC 1767 🔒](https://leetcode.com/problems/leetflex-banned-accounts/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=leetflex-banned-accounts) |
| 17 | Product Price at a Given Date | Medium / Removed from sections | [LC 1393 🔒](https://leetcode.com/problems/product-price-at-a-given-date/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=product-price-at-a-given-date) |
| 18 | **Friday Purchases I** | Medium / Removed from sections | [LC 2994 🔒](https://leetcode.com/problems/friday-purchases-i/) | [Run in Browser 💻](https://naveen99c.github.io/sql/sql_sandbox.html?slug=friday-purchases-i) |



---

## 📋 All 44 LeetCode Hard SQL Problems

> **Legend:** ⭐ = Must-Do · 🔒 = Premium · Pattern numbers refer to the 12 core patterns.

| # | LC# | Problem | Pattern(s) |
|---|-----|---------|------------|
| 1 | 185 | ⭐ Department Top Three Salaries | Ranking |
| 2 | 262 | ⭐ Trips and Users | Self-Joins, Anti-Join |
| 3 | 569 | ⭐ Median Employee Salary | Subqueries/CTEs, Ranking |
| 4 | 571 | ⭐ Median Given Frequency of Numbers | Window Frame, Special |
| 5 | 579 | ⭐ Find Cumulative Salary of an Employee | LAG/LEAD, Window Frame |
| 6 | 601 | ⭐ Human Traffic of Stadium | Gaps & Islands, LAG/LEAD |
| 7 | 615 | ⭐ Average Salary: Departments vs Company | GROUP BY + HAVING, Date |
| 8 | 618 | ⭐ Students Report By Geography | Pivoting, Ranking |
| 9 | 1097 | ⭐ Game Play Analysis V | Date, Subqueries |
| 10 | 1159 | ⭐ Market Analysis II | Ranking, Self-Joins |
| 11 | 1194 | Tournament Winners | Ranking, GROUP BY |
| 12 | 1225 | Active Businesses | Gaps & Islands, GROUP BY |
| 13 | 1270 | Process Tasks Using Servers | Recursive CTE |
| 14 | 1285 | Active Users | Gaps & Islands |
| 15 | 1336 | Find the Quiet Students in All Exams | Recursive CTE, Ranking |
| 16 | 1369 | Average Selling Price | Ranking, Date |
| 17 | 1384 | Median Employee Salary | Recursive CTE |
| 18 | 1412 | Number of Comments per Post | Ranking, Self-Join |
| 19 | 1479 | ⭐ Sales by Day of the Week | Date, Pivoting, Anti-Join |
| 20 | 1613 | Find the Missing IDs | Recursive CTE, Anti-Join |
| 21 | 1635 | Hopper Company Queries I | Recursive CTE, Date |
| 22 | 1645 | Hopper Company Queries II | Recursive CTE, Date |
| 23 | 1651 | Tree Node | Recursive CTE, LAG/LEAD |
| 24 | 1767 | Leetflex Banned Accounts | Recursive CTE, Self-Join |
| 25 | 1917 | Leetcodify Friends Recommendations | Self-Join, Anti-Join |
| 26 | 1972 | New Users Daily Count | Ranking, Date |
| 27 | 2010 | Account Balance | Ranking, Window Frame |
| 28 | 2118 | Invalid Tweets | String/CONCAT |
| 29 | 2153 | Count Salary Categories | Recursive CTE, CASE |
| 30 | 2173 | Longest Subsequence With Limited Sum | Gaps & Islands |
| 31 | 2199 | Strong Friendship | String/CONCAT, Self-Join |
| 32 | 2252 | Dynamic Pivoting of a Table | Pivoting, Special |
| 33 | 2253 | Build a Matrix With Conditions | CTE, Special |
| 34 | 2362 | Steps to Make Array Non-decreasing | Ranking |
| 35 | 2474 | Customers with Strictly Increasing Purchases | Self-Joins, Gaps & Islands |
| 36 | 2494 | Count Salary Categories | Window Frame |
| 37 | 2701 | Consecutive Transactions with Increasing Amounts | Gaps & Islands |
| 38 | 2720 | Number of Unique Categories | Ranking |
| 39 | 2752 | Consecutive Transactions | Gaps & Islands |
| 40 | 2793 | Count of Good Partitions | Ranking |
| 41 | 2991 | Rearrange Products Table | Pivoting, CONCAT |
| 42 | 2993 | Count Salary Categories | Date |
| 43 | 2994 | Friday Purchases I | Date |
| 44 | 2995 | Count of Interesting Subarrays | Ranking |

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
> LC 185, 262, 569, 571, 579, 601, 615, 618, 1097, 1159, 1479

---

*Based on patterns from [luuck25/sql](https://github.com/luuck25/sql/blob/main/patterns.md), expanded with intuition, technical details, and worked examples.*
