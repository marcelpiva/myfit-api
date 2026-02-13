"""Schedule router for appointment management.

This is the main entry point that composes all schedule sub-routers:
- appointments_router: Appointment CRUD, analytics, attendance, group sessions, evaluations, calendar export
- availability_router: Availability management, conflict detection, booking, trainer settings
- recurring_router: Auto-generate, duplicate week, waitlist, session templates
"""
from fastapi import APIRouter

from .appointments_router import appointments_router
from .availability_router import availability_router
from .recurring_router import recurring_router

router = APIRouter(prefix="/schedule", tags=["schedule"])

router.include_router(appointments_router)
router.include_router(availability_router)
router.include_router(recurring_router)
