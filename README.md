## 📅 Project Timeline (Visual Gantt Chart)

### T2 2026 Core Development
```mermaid
gantt
    title EDAPT v2 - T2 2026 Core Development Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  %W
    
    section Planning & Setup
    DB Schema & Data Ingestion    :a1, 2026-07-06, 21d
    UI Wireframing & Tech Stack   :a2, 2026-07-06, 14d
    
    section Mode 1 (Descriptive)
    Dashboard Development         :a3, after a2, 21d
    Week 6 Check-in Prototype     :milestone, m1, 2026-08-14, 0d
    
    section Mode 2 (Predictive)
    Train ML Model (T2 2025 Data) :a4, 2026-08-17, 21d
    Week 9 Check-in Prototype     :milestone, m2, 2026-09-04, 0d
    
    section Finalization
    Gemini API Integration        :a5, 2026-09-07, 14d
    Testing & Documentation       :a6, 2026-09-14, 14d
    Final Submission              :milestone, m3, 2026-09-28, 0d