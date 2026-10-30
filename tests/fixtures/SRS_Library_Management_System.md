# Software Requirements Specification
## Library Management System (LMS)

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-10-28 |
| Status | Baseline |

---

## 1. Introduction

### 1.1 Purpose
This document specifies the software requirements for the Library Management System (LMS), a small in-memory application that lets library staff manage a catalog of books, register members, lend and return books, apply overdue fines, and produce operational reports.

### 1.2 Scope
The LMS covers:
- Catalog management (adding, removing, looking up, searching and listing books).
- Member management (registration, membership tiers, borrowing eligibility, fines and payments).
- Lending (checkout, return, renewal and overdue detection).
- Fine calculation.
- Reporting (inventory, authors, member activity, overdue loans, fines).
- A demonstration scenario that exercises the main workflow.

Out of scope: persistent storage, user interfaces beyond console output, authentication, reservations and holds.

### 1.3 Definitions
| Term | Definition |
|---|---|
| ISBN | International Standard Book Number; identifies a title in the catalog. |
| Title / Book | A catalog entry identified by ISBN, which may have several physical copies. |
| Copy | One physical item of a book that can be lent out. |
| Member | A registered library patron identified by a unique member ID. |
| Membership type | The member's tier: `standard`, `premium` or `staff`. |
| Loan | A record that one copy of a book was lent to one member. |
| Due date | The date by which a loaned copy must be returned. |
| Overdue | A loan whose reference date (return date, or the check date when not yet returned) is after its due date. |
| Grace period | Number of overdue days for which no fine is charged. |

---

## 2. Overall Description

### 2.1 Product Perspective
The LMS is a self-contained Python package. It is organised into a data model layer (books, members, loans), a service layer (catalog, lending, fines) and a reporting layer that reads from the services.

### 2.2 User Classes
- **Librarian**: manages the catalog, registers members, records checkouts and returns, collects fines and runs reports.
- **Developer / Tester**: runs the demonstration scenario to confirm the system works end to end.

### 2.3 Operating Environment
Any platform with Python 3.8 or later.

### 2.4 Constraints and Assumptions
- All data lives in memory for the lifetime of the process.
- Dates are calendar dates without times.
- Monetary amounts are in a single currency and rounded to two decimal places.

---

## 3. Specific Requirements: Functional

### 3.1 Catalog Management

**FR-001 — Maintain catalog**
The system shall maintain a catalog of books keyed by ISBN, starting empty, and shall be able to return the full list of books in the catalog.

**FR-002 — Add a book**
The system shall allow a librarian to add a book with ISBN, title, author, publication year and number of copies (default 1). The system shall reject the book when:
- the ISBN, ignoring hyphens, does not contain exactly 10 or 13 characters;
- the number of copies is less than 1;
- the publication year is later than the current year.

A newly added book shall have all of its copies available.

**FR-003 — Merge copies for an existing ISBN**
When a book is added with an ISBN that already exists in the catalog, the system shall not create a new entry; instead it shall increase both the total and the available copy counts of the existing book by the number of copies added, and return the existing book.

**FR-004 — Remove a book**
The system shall allow a book to be removed from the catalog by ISBN. Removal shall be refused while any copy of that book is on loan (available copies differ from total copies).

**FR-005 — Look up a book**
The system shall return the book for a given ISBN, and shall raise an error stating that no book exists when the ISBN is not in the catalog.

**FR-006 — Search the catalog**
The system shall return all books whose title or author contains a given keyword, ignoring letter case.

**FR-007 — List available books**
The system shall list the books that have at least one available copy, sorted alphabetically by title.

**FR-032 — Search by publication year**
The system shall return all books whose publication year falls within a given range, inclusive of both bounds.

**FR-036 — Search by ISBN**
Keyword search (FR-006) shall also match a book's ISBN, ignoring hyphens, in addition to its title and author.

**FR-008 — Track copy availability**
When a copy is checked out, the system shall decrease the book's available copies by one, and shall refuse the checkout when no copies are available. When a copy is returned, the system shall increase the available copies by one, and shall refuse the return when all copies are already in stock.

**FR-009 — Export a book record**
The system shall provide a dictionary representation of a book containing its ISBN, title, author, year, total copies and available copies.

### 3.2 Member Management

**FR-010 — Create a member**
The system shall create a member with a member ID, name, email address and membership type (default `standard`). The email address shall match the pattern `local-part@domain.tld`; otherwise the member shall be rejected. The membership type shall be one of the supported tiers (see FR-012); otherwise the member shall be rejected. A new member shall have no active loans and zero outstanding fines.

**FR-011 — Register members**
The system shall register members with the lending service and shall reject a registration whose member ID is already registered.

**FR-012 — Borrowing limits**
The maximum number of simultaneous active loans shall depend on the membership type:

| Membership type | Borrowing limit |
|---|---|
| standard | 3 |
| premium | 7 |
| staff | 10 |

**FR-013 — Borrowing eligibility**
A member shall be eligible to borrow only when they have no outstanding fines and their number of active loans is below their borrowing limit.

**FR-014 — Record fines**
The system shall add a fine amount to a member's outstanding fines, rounded to two decimals. Negative fine amounts shall be rejected.

**FR-015 — Pay fines**
The system shall allow a member to pay part or all of their outstanding fines and shall return the remaining balance. The payment shall be rejected if it is zero or negative, or if it exceeds the outstanding balance.

**FR-033 — Deactivate a member**
The system shall allow a librarian to deactivate a member. A deactivated member shall not be eligible to borrow books.

**FR-035 — Payment history**
When a member pays a fine, the system shall return the remaining balance and shall record the amount and date of each payment in the member's payment history.

### 3.3 Lending

**FR-016 — Check out a book**
The system shall check out a book (by ISBN) to a registered member (by member ID). The checkout shall be refused if the member is not eligible to borrow (FR-013). On success the system shall reduce the book's available copies, create a loan with a unique, sequentially assigned loan ID starting at 1, attach the loan to the member's active loans and record it in the lending service. The loan start date shall default to today's date if not supplied.

**FR-017 — Loan period**
The due date of a new loan shall be 14 days after its start date.

**FR-018 — One copy per title per member**
The system shall refuse a checkout when the member already has an active loan for the same ISBN.

**FR-019 — Return a book**
The system shall record the return of a loan by loan ID, with the return date defaulting to today. The system shall refuse to return a loan that was already returned. On return the system shall mark the loan as returned, increase the book's available copies and remove the loan from the member's active loans.

**FR-020 — Renew a loan**
The system shall allow a loan to be renewed, extending the due date by another 14-day loan period, and shall return the new due date. A loan shall be renewed at most 2 times. Renewal shall be refused if the loan has been returned or is currently overdue.

**FR-021 — Overdue detection**
The system shall compute the number of days a loan is overdue, using the return date if the loan has been returned, otherwise a supplied check date, otherwise today. The value shall never be negative. The system shall list all loans that are not yet returned and are overdue as of a given date.

**FR-031 — Due-date reminders**
The system shall send an email reminder to a member 2 days before each of their loans is due.

**FR-034 — Renewal eligibility**
A loan shall be renewed only when it has been renewed fewer than 2 times and the borrowing member has no outstanding fines.

### 3.4 Fines

**FR-022 — Fine calculation**
The fine for a loan shall be calculated as follows:
- If the loan is overdue by 2 days or fewer (grace period), the fine is 0.00.
- Otherwise the fine is the number of overdue days multiplied by 0.50 per day.
- The fine for a single loan shall not exceed 20.00.
- The result shall be rounded to two decimals.

**FR-023 — Charge fine on return**
When a book is returned, the system shall calculate the fine for that loan and, if it is greater than zero, add it to the member's outstanding fines. The return operation shall report the fine charged.

**FR-024 — Total outstanding fines**
The system shall compute the total of outstanding fines across a set of members, rounded to two decimals.

### 3.5 Reporting

**FR-025 — Inventory summary**
The system shall report the number of titles, the total number of copies, the number of available copies and the number of copies on loan.

**FR-026 — Titles per author**
The system shall report the number of titles per author, ordered by count descending and then by author name ascending.

**FR-027 — Member activity**
The system shall report, for each registered member, the member ID, name, number of active loans, borrowing limit and outstanding fines, ordered by member ID.

**FR-028 — Overdue loans report**
The system shall report, for each overdue loan as of a given date, the loan ID, member ID, ISBN, days overdue and the projected fine if returned on that date.

**FR-029 — Fines summary**
The system shall report the total outstanding fines across all registered members and the number of members with outstanding fines greater than zero.

### 3.6 Demonstration

**FR-030 — Demonstration scenario**
The system shall provide a runnable demonstration that:
1. builds a sample catalog of three books and registers two members (one standard, one premium);
2. creates one checkout dated 20 days in the past and one current checkout;
3. prints the inventory summary and overdue report;
4. returns the late loan and prints the fine charged;
5. prints the fines summary.

---

## 4. Specific Requirements: Non-Functional

**NFR-001 — Portability**
The system shall run on Python 3.8 or later and shall use only the Python standard library.

**NFR-002 — Storage**
The system shall keep all data in memory and shall not require a database or files.

**NFR-003 — Error reporting**
Every rejected operation shall raise an exception with a human-readable message describing the cause.

---

## 5. Traceability
Requirement-to-code traceability is maintained separately in the gold-standard mapping (`gold_standard_mapping.json` / `.csv`). Non-functional requirements NFR-001 to NFR-003 are cross-cutting and are not traced to specific code locations.
