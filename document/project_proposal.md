## APRIL 4

Capstone Project Student
Authored by: Nitesh Bhatta(20035193), Koshish
Shrestha(20035518), Sangam Ghale Gurung (20035219),
Gyani Bohara(12200068), Griffins Leshan(20029671)

# Educational Data Analytics and

# Predictive Tool (EDAPT) v


## Table of Contents

- KOI Cover Page
- Executive Summary
- Introduction
- Goals
- Project Plan
   - Project Design Methodology
   - Project timelines
   - 1. Trimester 1, 2026 (T1 2026) - Core Platform Development
   - 2. Trimester 2, 2026 (T2 2026) - System Extension & LTI Integration
- Project Team.........................................................................................................................................
- Conclusion and Recommendations
- Reference List


## KOI Cover Page


## Executive Summary

This project outlines the development of the Educational Data Analytics and Predictive Tool (EDAPT)
v2 for King's Own Institute (KOI). Educational institutions collect vast amounts of student and
performance data, but identifying actionable insights from raw, tabular data remains a significant
challenge. The project owner, Ken Emeleus (Head of Technology Services), requires a robust platform
that leverages anonymized institutional data to visualize academic performance and predict student
outcomes.

Our proposed solution is a dual-mode analytics platform and predictive engine. Mode 1 will provide
Descriptive Analytics via an interactive dashboard focusing on historical performance trends, while
Mode 2 will utilize machine learning to predict student success (Pass/Fail) in future trimesters. By
implementing a modern web architecture (Python, React/Dash, PostgreSQL) combined with Google
Gemini API for natural language insights, EDAPT v2 will enable data-driven decision-making for
academic and faculty staff.


## Introduction

King's Own Institute (KOI) is dedicated to success in higher education. In the context of modern
education, leveraging data is crucial for improving student retention and academic success. Currently,
the institution possesses an anonymised dataset mapping students, lecturers, and countries to unique
identifiers.
However, without a dedicated analytical platform, it is difficult to quickly ascertain trimester-on-
trimester growth, peer comparisons, or institutional measures such as attrition risk and grade inflation.
The current situation requires an intuitive, visual, and predictive system to transform this raw data into
strategic insights.

## Goals

- **Clearly identify the problem:** Academic staff currently lack a unified, predictive tool to easily
    explore historical assessment data, monitor subject difficulty, or identify international cohorts
    requiring additional support. There is also a lack of early warning systems to predict which
    students might fail future subjects based on historical trends.
- **Clearly identify your proposed solution:** We will develop EDAPT v2, an application divided into
    two operational modes. Mode 1 will be a visual dashboard for descriptive analytics, and Mode
    2 will be a predictive validation model tested against T3 2025 data.
- **Give reasons why and how it will work:** The platform will be built on a robust Python backend
    (FastAPI/Flask) utilising strong data science libraries like Pandas and Scikit-learn to process the
    data. A modern frontend (React.js or Dash) will allow users to filter by Year, Trimester, Subject,
    and Lecturer. The inclusion of Google Gemini API will allow users to ask natural language
    queries, such as "Summarize the performance trends for ICT104," making the data accessible
    to non-technical staff.
- **Describe the potential impact:** The solution will enable data-driven decision-making, allowing
    staff to predict student success with a target accuracy of at least 75%, thereby enabling early
    interventions and reducing attrition risk.


## Project Plan

### Project Design Methodology

We have chosen a **Cross-Functional Agile Methodology**.

- **Reasons for this choice:** The project requires distinct milestone check-ins (Week 6 and Week
    9). Agile allows us to iteratively build Mode 1 (Descriptive) for the first check-in, gather
    feedback, and subsequently sprint towards Mode 2 (Predictive). Additionally, matrix task
    delegation ensures every team member contributes to both their primary domain (e.g.,
    documentation, UI) and the technical codebase simultaneously.

### Project timelines

The project development is divided across two trimesters to ensure a structured, iterative approach.
Trimester 1 , 2026 focuses on the core functionality (Mode 1 and Mode 2), while Trimester 2 , 2026
focuses on system extension, real-time integration, and stakeholder handover.

The EDAPT v2 project is structured across two distinct trimesters to ensure a methodical progression
from core platform development to live integration. The following tables outline the key phases,
milestones, and deliverables for each term.

### 1. Trimester 1, 2026 (T1 2026) - Core Platform Development

**Timeline:** March 2, 2026 – May 18, 2026

**Focus:** Database ingestion, Descriptive Dashboard (Mode 1), and Predictive Model (Mode 2).

```
Timeframe Phase Key Deliverables & Milestones
```
```
Weeks 1 - 2 Planning & Setup
```
```
Project kickoff and repository initialization. PostgreSQL
database schema finalized (DrawSQL), raw masked data
ingested, and UI wireframes (Figma) approved.
```
```
Weeks 3 - 6 Mode 1
Development
```
```
React/Dash frontend connected to FastAPI backend.
Interactive UI components and visualisations (Plotly/D3)
built and tested.
```
```
Week 6 Milestone 1 Check-in 1 (Apr 13):^ Descriptive analytics dashboard
prototype presented to stakeholders.
```
```
Weeks 7 - 9 Mode 2 Development
```
```
Data cleaned and feature engineering complete. Machine
learning model (e.g., XGBoost/RF) trained on T2 2025 data.
Predictive API endpoints established.
```
```
Week 9 Milestone 2
```
```
Check-in 2 (May 4): Predictive model validation results
presented. Target >75% accuracy KPI achieved.
```

```
Weeks 10 -
11
```
```
AI Integration &
Polish
```
```
Google Gemini API integrated via prompt engineering for
natural language insights. System Documentation and White
Paper drafted. End-to-end QA completed.
```
```
End of T
2026 Final Deliverable^
```
```
Final Submission (May 18): Fully functional local
deployment, White Paper, and AI Impact Report submitted
for grading.
```
```
Figure: EDAPT v2: Gantt chart representing T1 2026 Action Items
URL: https://github.com/KOI-Capstone-Project/EDAPTv2/tree/gantt-chart
```
### 2. Trimester 2, 2026 (T2 2026) - System Extension & LTI Integration

**Timeline:** June 29, 2026 – September 19, 2026

**Focus:** Live Moodle LTI integration, real-time data pipelines, and project handover to KOI IT.

```
Timeframe Phase Key Deliverables & Milestones
```
```
Weeks 1 - 4
```
```
Project
Planning &
Proposal
```
```
Course introduction, team formation, and project topic selection.
Intensive brainstorming, task distribution matrix finalized, and
formal Project Proposal completed.
```
```
Weeks 5 - 6
```
```
Core Setup &
Mode 1
```
```
Database schema (DrawSQL) and GitHub repository initialized. UI
wireframes (Figma) and API contracts finalized. FastAPI/React
boilerplate configured, and descriptive visualisations (Plotly/D3)
built.
```

**Week 6 Milestone 1 Check** presented to stakeholders. **- in 1 (Apr 13):**^ Descriptive analytics dashboard prototype

**Weeks 7 - 9**

```
Mode 2
Development
```
```
Data cleaned and feature engineering complete. Machine learning
model (e.g., XGBoost/RF) trained on T2 2025 data. Predictive API
endpoints established and tested.
```
**Week 9 Milestone 2**

```
Check-in 2 (May 4): Predictive model validation results presented.
Target >75% accuracy KPI achieved.
```
**Weeks 10 -
11**

```
Finalization &
Docs
```
```
Google Gemini API integrated via prompt engineering. Final
System & API Documentation compiled. White Paper drafted. End-
to-end bug fixing and QA.
```
**End of T
2026**

```
Final
Deliverable
```
```
Final Submission (May 18): Fully functional local deployment,
White Paper, and System Documentation formally submitted for
grading.
```
```
Figure: EDAPT v2: Gantt chart representing T2 2026 Action Items
```
```
URL: https://github.com/KOI-Capstone-Project/EDAPTv2/tree/gantt-chart
```

## Project Team.........................................................................................................................................

The following table outlines the task distribution matrix:

```
Task Member Name Tech Contributions
```
```
Project Management /
Backend API
```
```
Nitesh Leading model selection, Google Gemini AI
integration, and core predictive logic.
```
```
Documentations / White
Paper Sangam^
```
```
Documenting predictive thinking, evaluating AI
impact, and EDA scripting.
```
```
UI/UX & Dashboard Koshish Building the React/Dash interface and the Mode 1 visualization engine.
```
```
Slides & Data Queries Griffins Preparing milestone presentations and writing
SQL/Python logic for prototype measures.
```
```
Data Engineer / QA Gyani
```
```
Schema creation, local deployment testing, and
validating 75% accuracy KPIs.
```

## Conclusion and Recommendations

The EDAPT v2 project addresses KOI's need to transform raw, anonymized institutional data into a
predictive asset. By developing a dual-mode platform encompassing both descriptive and predictive
analytics, academic staff will be empowered to make data-driven decisions that actively monitor
student success, subject difficulty, and grade distribution.

We recommend proceeding with the proposed modern architecture stack (Python, React,
PostgreSQL) and the defined Agile milestone schedule. This approach guarantees a 100% functional
local deployment and comprehensive documentation regarding ethical considerations and predictive
bias by the end of Trimester 1, 2026.


## Reference List

- Emeleus, K. (2026). _Project definition: Educational Data Analytics and Predictive Tool (EDAPT)_
    _v2_. King's Own Institute.
- Google. (2024). _Gemini API documentation: Building generative AI applications_. Google AI for
    Developers. https://ai.google.dev/docs
- King's Own Institute. (n.d.). _Success in higher education_. Retrieved March 27, 2026, from KOI
    internal resources.
- Meta Platforms, Inc. (2026). _React: The library for web and native user interfaces_.
    https://react.dev/
- Office of the Australian Information Commissioner. (2024). _Guide to data analytics and the_
    _Australian privacy principles_. https://www.oaic.gov.au/


