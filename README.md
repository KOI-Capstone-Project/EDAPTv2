## 📅 Project Timeline

### Phase 1: T1 2026 (Core Development)
This phase focuses on building the foundational database, Mode 1 (Descriptive Dashboard), and Mode 2 (Predictive Engine).

```mermaid
%%{init: {'gantt': {'leftPadding': 200, 'rightPadding': 200}}}%%
gantt
    title EDAPT v2 - T1 2026 Realistic Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d
    tickInterval 7 day
    todayMarker off
    
    section Planning & Setup
    T1 Officially Starts            :milestone, start, 2026-03-02, 0d
    Course Intro & Team Formation   :p1, 2026-03-02, 14d
    Project Topic Selection         :p2, 2026-03-16, 7d
    Brainstorming & Task Dist.      :p3, 2026-03-23, 7d
    Project Proposal Finalization   :p4, 2026-03-23, 7d
    DB Schema & Repo Init           :a1, 2026-03-30, 4d
    UI Wireframing (Figma)          :a2, 2026-03-30, 4d
    API Contract Definition         :a3, 2026-03-30, 4d
    
    section Mode 1 (Descriptive)
    FastAPI & React Boilerplate     :b1, 2026-04-03, 3d
    Descriptive API Endpoints       :b2, after b1, 4d
    UI Component Build (Filters)    :b3, 2026-04-03, 4d
    Chart Integration (Plotly/D3)   :b4, after b3, 4d
    Mode 1 Integration Testing      :b5, 2026-04-10, 3d
    Week 6 Check-in Prototype       :milestone, m1, 2026-04-13, 0d
    
    section Mode 2 (Predictive)
    T2 2025 Data Cleaning & Prep    :c1, 2026-04-13, 5d
    Feature Engineering             :c2, after c1, 5d
    Model Training (XGBoost/RF)     :c3, after c2, 6d
    Accuracy Validation (>75% KPI)  :c4, after c3, 5d
    Predictive API Endpoints        :c5, after c3, 5d
    Week 9 ML Check-in              :milestone, m2, 2026-05-04, 0d
    
    section Finalization & Docs
    Gemini Prompt Eng & API         :d1, 2026-05-04, 5d
    Compile Final System Docs       :d2, 2026-05-04, 7d
    White Paper Drafting            :d3, 2026-05-04, 7d
    End-to-End Bug Fixing & QA      :d4, 2026-05-11, 7d
    T1 Final Submission             :milestone, m3, 2026-05-18, 0d
```

### Phase 2: T2 2026 (Live Integration & Handover)
This future phase focuses on integrating the system with Moodle via LTI and handing the project over to KOI IT.
```mermaid
%%{init: {'gantt': {'leftPadding': 220, 'rightPadding': 200}}}%%
gantt
    title EDAPT v2 - T2 2026 Detailed Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d
    tickInterval 7 day
    todayMarker off
    
    section LTI Setup & Auth
    T2 Officially Starts            :milestone, start, 2026-06-29, 0d
    LTI 1.3 Architecture Review     :b1, 2026-06-29, 5d
    OAuth2 Security Implementation  :b2, after b1, 7d
    LTI Launch Endpoints Dev        :b3, after b2, 8d
    Role Mapping (Student/Staff)    :b4, after b2, 5d
    
    section Live Data Pipeline
    Real-Time API Sync Endpoints    :b5, 2026-07-20, 10d
    Data Pipeline Stress Testing    :b6, after b5, 7d
    Staging Environment Deployment  :b7, after b6, 5d
    Live Moodle Test Connection     :b8, after b7, 5d
    Week 7 LTI Live Milestone       :milestone, m4, 2026-08-17, 0d
    
    section UAT & Refinement
    Faculty UAT Environment Setup   :b9, 2026-08-17, 4d
    Conduct UAT Sessions            :b10, after b9, 7d
    Incorporate UAT Feedback/Fixes  :b11, after b10, 5d
    UAT Sign-off & Approval         :milestone, m5, 2026-08-31, 0d
    
    section Final Handover
    IT Operations Manual Draft      :b12, 2026-09-01, 7d
    Production Deployment Scripts   :b13, after b12, 6d
    Codebase Cleanup & Comments     :b14, after b12, 5d
    Final Stakeholder Presentation  :b15, after b13, 4d
    Project Handover Complete       :milestone, m6, 2026-09-19, 0d
```