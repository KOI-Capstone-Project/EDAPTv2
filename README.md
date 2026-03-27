## 📅 Project Timeline

### Phase 1: T1 2026 (Core Development)
This phase focuses on building the foundational database, Mode 1 (Descriptive Dashboard), and Mode 2 (Predictive Engine).

```mermaid
%%{init: {'gantt': {'leftPadding': 150}}}%%
gantt
    title EDAPT v2 - T1 2026 Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d
    
    section Planning & Setup
    DB Schema & Data Ingestion    :a1, 2026-03-02, 14d
    UI Wireframing & Tech Stack   :a2, 2026-03-02, 14d
    
    section Mode 1 (Descriptive)
    Dashboard Development         :a3, after a2, 21d
    Week 6 Check-in Prototype     :milestone, m1, 2026-04-13, 0d
    
    section Mode 2 (Predictive)
    Train ML Model (T2 2025 Data) :a4, after a3, 21d
    Week 9 Check-in Prototype     :milestone, m2, 2026-05-04, 0d
    
    section Finalization
    Gemini API Integration        :a5, after a4, 10d
    Testing & Documentation       :a6, after a4, 14d
    T1 Final Submission           :milestone, m3, 2026-05-18, 0d
```

### Phase 2: T2 2026 (Live Integration & Handover)
This future phase focuses on integrating the system with Moodle via LTI and handing the project over to KOI IT.
```mermaid
%%{init: {'gantt': {'leftPadding': 150}}}%%
gantt
    title EDAPT v2 - T2 2026 Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d
    
    section LTI Setup
    Moodle Integration Planning   :b1, 2026-06-29, 14d
    API Security & Auth (LTI)     :b2, after b1, 14d
    
    section Live Pipeline
    Real-Time Data Sync           :b3, after b2, 21d
    Week 7 LTI Live Milestone     :milestone, m4, 2026-08-17, 0d
    
    section UAT & Handover
    User Acceptance Testing (UAT) :b4, after b3, 14d
    UAT Sign-off                  :milestone, m5, 2026-08-31, 0d
    Final Handover Prep & Docs    :b5, after b4, 19d
    Project Handover Complete     :milestone, m6, 2026-09-19, 0d
```