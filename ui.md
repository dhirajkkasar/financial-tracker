# Personal Finance Tracker – Frontend UI Specification

## 1. Design Principles

* **Read-only UI**
* **Data-dense, minimal interaction**
* **Fast load using aggregated APIs**
* Focus on:

  * Net worth
  * XIRR
  * Goal progress
  * Allocation clarity

---

## 2. Navigation Structure

Tabs:

1. **Overview**
2. **Equity**
3. **Debt**
4. **Gold**
5. **Real Estate**
6. **Retirement (EPF/PPF/NPS)**
7. **Important Data**

👉 Tabs correspond to **asset classes**

---

## 3. Overview Tab (🔥 Most Important)

### 3.1 Top Summary Section

Display:

* **Total Net Worth**
* **Total Invested**
* **Absolute Gain**
* **Portfolio XIRR**

---

### 3.2 Asset Class XIRR Summary

Show:

| Asset Class | XIRR | Current Value |
| ----------- | ---- | ------------- |
| Equity      | %    | ₹             |
| Debt        | %    | ₹             |
| Gold        | %    | ₹             |
| Others      | %    | ₹             |

---

### 3.3 Goal Tracking Section

For each goal:

Display:

* Goal Name
* Target Amount
* Current Value
* % Completed
* Remaining Amount
* Target Date

---

### 3.4 Goal Progress Visualization

* Progress bar per goal
* Color coding:

  * <50% → red
  * 50–80% → yellow
  * > 80% → green

---

### 3.5 Required Investment Insight

For each goal:

* Required monthly investment (SIP)
* Time remaining (months/years)

---

### 3.6 Allocation Overview (Optional)

* Pie chart:

  * Equity vs Debt vs Others

---

## 4. Asset Class Tabs (Equity / Debt / etc.)

Each tab represents **one asset class**

---

## 4.1 Tab Summary Section

Display:

* Total value (asset class)
* Total invested
* XIRR (asset class)

---

## 4.2 Investment List

Table format:

| Investment | Platform | Current Value | Invested | XIRR | Status |
| ---------- | -------- | ------------- | -------- | ---- | ------ |

---

### Status Handling

* **Active investments**

  * normal display

* **Closed / Old investments**

  * grayed out OR
  * toggle filter: “Show inactive”

---

## 4.3 Investment-Level Metrics

Each row shows:

* current value
* invested amount
* XIRR

---

## 4.4 Sorting / Filtering

Basic capabilities:

* sort by:

  * value
  * XIRR
* filter:

  * active / inactive

---

## 5. Important Data Tab

Displays:

* Bank accounts
* Insurance policies
* Folio numbers
* Notes

---

### Layout

| Category | Name | Value | Notes |
| -------- | ---- | ----- | ----- |

---

## 6. UI Behavior

### 6.1 Real-Time Updates

* On page load:

  * fetch latest data from backend
  * reflect latest NAV / prices

---

### 6.2 No Editing in UI

* All updates via CLI/API
* UI strictly read-only

---

## 7. API Dependencies

Frontend relies on:

* `/portfolio`
* `/allocation`
* `/investments`
* `/goals`
* `/metadata`

---

## 8. Performance Considerations

* Prefer **aggregated APIs**
* Avoid multiple round trips
* Cache responses at frontend (optional)

---

## 9. Future Enhancements

* Drilldown pages (investment-level charts)
* Goal projection graphs
* Historical net worth chart
* Alerts (goal lagging, allocation drift)

---

## 10. Summary

UI focuses on answering:

1. **What is my net worth?**
2. **How is my money allocated?**
3. **How am I performing (XIRR)?**
4. **Am I on track for my goals?**
5. **What should I invest next?**

