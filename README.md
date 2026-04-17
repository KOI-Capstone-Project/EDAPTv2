sequenceDiagram
    participant Frontend as React Dashboard
    participant API as FastAPI (REST)
    participant Auth as JWT/Security
    participant DB as PostgreSQL

    Frontend->>API: GET /api/v1/subject/ICT101
    API->>Auth: Validate Token
    Auth-->>API: Token Valid (Lecturer Access)
    API->>DB: SELECT * FROM enrollment WHERE subject='ICT101'
    DB-->>API: Raw Data Rows
    API->>API: Process through Pydantic (Validation)
    API-->>Frontend: JSON Data Response
    Frontend->>Frontend: Render Plotly Charts