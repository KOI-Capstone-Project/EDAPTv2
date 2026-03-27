## 📅 Project Timeline

### Phase 1: T1 2026 (Core Development)
This phase focuses on building the foundational database, Mode 1 (Descriptive Dashboard), and Mode 2 (Predictive Engine).

```mermaid
%%{init: {'gantt': {'leftPadding': 150, 'rightPadding': 150}}}%%
gantt
    title EDAPT v2 - T1 2026 Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d
    
    section Planning & Setup
    Requirement Analysis & Roles  :a1, 2026-03-02, 7d
    DB Schema & PostgreSQL Setup  :a2, 2026-03-09, 7d
    Anonymised Data Ingestion     :a3, 2026-03-09, 7d
    UI Wireframing (React/Dash)   :a4, 2026-03-09, 7d
    
    section Mode 1 (Descriptive)
    Backend API for Dashboard     :a5, 2026-03-16, 14d
    Interactive Dashboard UI      :a6, 2026-03-16, 21d
    Visualisations (Trends/Peers) :a7, 2026-03-30, 14d
    Week 6 Check-in Prototype     :milestone, m1, 2026-04-13, 0d
    
    section Mode 2 (Predictive)
    Data Preprocessing (T2 2025)  :a8, 2026-04-13, 7d
    Algorithm Selection & Config  :a9, 2026-04-20, 7d
    Model Training & Validation   :a10, 2026-04-27, 7d
    Week 9 Check-in Prototype     :milestone, m2, 2026-05-04, 0d
    
    section Finalization
    Google Gemini API Integration :a11, 2026-05-04, 7d
    System Docs & White Paper     :a12, 2026-05-11, 7d
    T1 Final Submission           :milestone, m3, 2026-05-18, 0d
```

### Phase 2: T2 2026 (Live Integration & Handover)
This future phase focuses on integrating the system with Moodle via LTI and handing the project over to KOI IT.
```mermaid
%%{init: {'gantt': {'leftPadding': 150, 'rightPadding': 150}}}%%
gantt
    title EDAPT v2 - T2 2026 Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d
    
    section LTI Setup
    Moodle LTI Architecture Review:b1, 2026-06-29, 14d
    Auth & Security Implementation:b2, 2026-07-13, 14d
    
    section Live Pipeline
    Real-Time Data Sync Endpoints :b3, 2026-07-27, 14d
    Live Integration Testing      :b4, 2026-08-10, 7d
    Week 7 LTI Live Milestone     :milestone, m4, 2026-08-17, 0d
    
    section UAT & Handover
    Faculty UAT Setup & Training  :b5, 2026-08-17, 7d
    User Acceptance Testing (UAT) :b6, 2026-08-24, 7d
    UAT Sign-off                  :milestone, m5, 2026-08-31, 0d
    Final IT Handover Docs        :b7, 2026-09-01, 18d
    Project Handover Complete     :milestone, m6, 2026-09-19, 0d
```