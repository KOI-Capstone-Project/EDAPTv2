## 📅 Project Timeline

### Phase 1: T1 2026 (Core Development)
This phase focuses on building the foundational database, Mode 1 (Descriptive Dashboard), and Mode 2 (Predictive Engine).

```mermaid
%%{init: {'gantt': {'leftPadding': 180, 'rightPadding': 200}}}%%
gantt
    title EDAPT v2 - T1 2026 Detailed Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d
    
    section Planning & Setup
    T1 Officially Starts            :milestone, start, 2026-03-02, 0d
    Project Kickoff & GitHub Repo   :a1, 2026-03-02, 3d
    DB Schema Design (DrawSQL)      :a2, after a1, 3d
    PostgreSQL Setup & Ingestion    :a3, after a2, 5d
    UI Wireframing (Figma)          :a4, 2026-03-02, 7d
    API Contract Definition         :a5, after a4, 4d
    
    section Mode 1 (Descriptive)
    FastAPI Boilerplate & Routers   :a6, 2026-03-16, 5d
    Descriptive API Endpoints       :a7, after a6, 7d
    React/Dash Layout & Routing     :a8, 2026-03-16, 5d
    UI Component Build (Filters)    :a9, after a8, 7d
    Chart Integration (Plotly/D3)   :a10, after a9, 10d
    Mode 1 Integration Testing      :a11, after a10, 5d
    Week 6 Check-in Prototype       :milestone, m1, 2026-04-13, 0d
    
    section Mode 2 (Predictive)
    T2 2025 Data Cleaning & Prep    :a12, 2026-04-13, 5d
    Feature Engineering             :a13, after a12, 4d
    Model Training (XGBoost/RF)     :a14, after a13, 6d
    Accuracy Validation (>75% KPI)  :a15, after a14, 4d
    Predictive API Endpoints        :a16, after a14, 4d
    Week 9 ML Check-in              :milestone, m2, 2026-05-04, 0d
    
    section Finalization
    Gemini Prompt Engineering       :a17, 2026-05-04, 3d
    LLM API Integration & UI        :a18, after a17, 5d
    White Paper: Predictive Logic   :a19, 2026-05-04, 7d
    System & API Documentation      :a20, after a19, 5d
    End-to-End Bug Fixing & QA      :a21, 2026-05-11, 7d
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