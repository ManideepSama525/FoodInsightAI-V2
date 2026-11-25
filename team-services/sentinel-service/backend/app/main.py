from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.request_logger import RequestLoggerMiddleware

# ---------------------------------------------------------
# API Routers
# ---------------------------------------------------------

from app.api.incident import router as incident_router
from app.api.simulator import router as simulator_router
from app.api.copilot import router as copilot_router
from app.api.dashboard import router as dashboard_router
from app.api.chart import router as chart_router
from app.api.reports import router as reports_router
from app.api.timeline import router as timeline_router
from app.api.mitre import router as mitre_router
from app.api.analyst import router as analyst_router
from app.api.campaign import router as campaign_router
from app.api.gateway import router as gateway_router
from app.api.integration import router as integration_router
from app.api.response_policy import router as response_policy_router


# ---------------------------------------------------------
# Database
# ---------------------------------------------------------

from app.database.database import engine
from app.models.incident import Base
from app.models.security_event import SecurityEvent  # noqa: F401
from app.models.response_policy_decision import ResponsePolicyDecision  # noqa: F401


# ---------------------------------------------------------
# Utilities
# ---------------------------------------------------------

from app.utils.seed_data import seed_demo_data


# ---------------------------------------------------------
# Create Database Tables
# ---------------------------------------------------------

from app.models.response_approval import ResponseApproval
from app.models.synthetic_ip_containment_action import SyntheticIPContainmentAction  # noqa: F401

Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------

app = FastAPI(
    title="Sentinel XDR API",
    description="AI Powered Autonomous Cyber Security Operations Center",
    version="1.0.0",
)


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)


# ---------------------------------------------------------
# Middleware
# ---------------------------------------------------------

app.add_middleware(
    RequestLoggerMiddleware
)


# ---------------------------------------------------------
# Register API Routers
# ---------------------------------------------------------

app.include_router(incident_router)

app.include_router(simulator_router)

app.include_router(copilot_router)

app.include_router(dashboard_router)

app.include_router(chart_router)

app.include_router(reports_router)

app.include_router(timeline_router)

app.include_router(mitre_router)

app.include_router(analyst_router)

app.include_router(campaign_router)

# ---------------------------------------------------------
# Security Gateway
# ---------------------------------------------------------

app.include_router(
    gateway_router
)
app.include_router(integration_router)
app.include_router(response_policy_router)



# ---------------------------------------------------------
# Root
# ---------------------------------------------------------

@app.get("/")
def root():

    return {
        "project": "Sentinel XDR",
        "status": "Running",
        "version": "1.0.0",
    }


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@app.get("/health")
def health():

    return {
        "database": "Connected",
        "backend": "Running",
    }


# ---------------------------------------------------------
# Login
# ---------------------------------------------------------

@app.get("/login")
def login():

    return {
        "message": "Dummy Login Page",
    }


# ---------------------------------------------------------
# Seed Demo Data
# ---------------------------------------------------------

@app.post("/seed")
def seed():

    return seed_demo_data()