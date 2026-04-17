# EDAPT v2 | Technical Architecture & API Design

This document outlines the system flow, data structures, and API endpoints for the EDAPT v2 Capstone project.

## 1. System Sequence Diagram
This diagram visualizes how the Frontend, FastAPI, and PostgreSQL database interact during a standard user request.

```mermaid
sequenceDiagram
    autonumber
    participant UI as React Frontend
    participant API as FastAPI (REST)
    participant Auth as JWT Security
    participant DB as PostgreSQL
    participant AI as Gemini AI Engine

    UI->>API: GET /api/v1/analytics/subject/ICT101
    API->>Auth: Validate Session Token
    Auth-->>API: Token Valid (Role: Lecturer)
    
    API->>DB: Fetch Anonymized Grade Data
    DB-->>API: Raw Data Result Set
    
    Note over API,AI: Optional: Trigger AI Insights
    API->>AI: Send Summary Statistics
    AI-->>API: Natural Language Insights
    
    API->>DB: Log Action to AUDIT_LOGS
    
    API-->>UI: JSON Response (Data + AI Insights)
    UI->>UI: Render Plotly Charts & Dashboard
```

## 2. Production API Architecture
The following diagram represents the "Security Gateway" design of our REST API.
```mermaid
graph TD
    subgraph Client_Layer [Frontend Interface]
        A[React Dashboard]
        B[Plotly Visualizations]
    end

    subgraph API_Layer [Backend Engine - FastAPI]
        C{REST API Gateway}
        D[Pydantic Data Validation]
        E[OAuth2 / JWT Auth]
    end

    subgraph Data_Layer [Storage & Processing]
        F[(PostgreSQL Database)]
        G[XGBoost ML Model]
        H[Audit Logger]
    end

    %% Connectivity
    A & B -->|HTTPS / JSON| C
    C --> E
    E --> D
    D --> F
    F --> G
    C --> H
    H --> F
```