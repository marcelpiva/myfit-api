"""Check-in service with database operations."""
import math
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.checkin.models import (
    CheckIn,
    CheckInCode,
    CheckInMethod,
    CheckInRequest,
    CheckInStatus,
    Gym,
    TrainerLocation,
)
from src.domains.organizations.models import OrganizationMembership, UserRole


class CheckInService:
    """Service for handling check-in operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # Gym operations

    async def get_gym_by_id(self, gym_id: uuid.UUID) -> Gym | None:
        """Get a gym by ID."""
        result = await self.db.execute(
            select(Gym)
            .where(Gym.id == gym_id)
            .options(selectinload(Gym.check_in_codes))
        )
        return result.scalar_one_or_none()

    async def list_gyms(
        self,
        organization_id: uuid.UUID | None = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Gym]:
        """List gyms."""
        query = select(Gym)

        if organization_id:
            query = query.where(Gym.organization_id == organization_id)
        if active_only:
            query = query.where(Gym.is_active == True)

        query = query.order_by(Gym.name).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_gym(
        self,
        organization_id: uuid.UUID,
        name: str,
        address: str,
        latitude: float,
        longitude: float,
        phone: str | None = None,
        radius_meters: int = 100,
    ) -> Gym:
        """Create a new gym."""
        gym = Gym(
            organization_id=organization_id,
            name=name,
            address=address,
            latitude=latitude,
            longitude=longitude,
            phone=phone,
            radius_meters=radius_meters,
        )
        self.db.add(gym)
        await self.db.commit()
        await self.db.refresh(gym)
        return gym

    async def update_gym(
        self,
        gym: Gym,
        name: str | None = None,
        address: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        phone: str | None = None,
        radius_meters: int | None = None,
        is_active: bool | None = None,
    ) -> Gym:
        """Update a gym."""
        if name is not None:
            gym.name = name
        if address is not None:
            gym.address = address
        if latitude is not None:
            gym.latitude = latitude
        if longitude is not None:
            gym.longitude = longitude
        if phone is not None:
            gym.phone = phone
        if radius_meters is not None:
            gym.radius_meters = radius_meters
        if is_active is not None:
            gym.is_active = is_active

        await self.db.commit()
        await self.db.refresh(gym)
        return gym

    # Check-in operations

    async def get_checkin_by_id(self, checkin_id: uuid.UUID) -> CheckIn | None:
        """Get a check-in by ID."""
        result = await self.db.execute(
            select(CheckIn)
            .where(CheckIn.id == checkin_id)
            .options(selectinload(CheckIn.gym))
        )
        return result.scalar_one_or_none()

    async def get_active_checkin(self, user_id: uuid.UUID) -> CheckIn | None:
        """Get user's active check-in (not checked out)."""
        result = await self.db.execute(
            select(CheckIn)
            .where(
                and_(
                    CheckIn.user_id == user_id,
                    CheckIn.checked_out_at.is_(None),
                    CheckIn.status == CheckInStatus.CONFIRMED,
                )
            )
            .options(selectinload(CheckIn.gym))
            .order_by(CheckIn.checked_in_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_checkins(
        self,
        user_id: uuid.UUID | None = None,
        gym_id: uuid.UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CheckIn]:
        """List check-ins with filters."""
        query = select(CheckIn).options(selectinload(CheckIn.gym))

        if user_id:
            query = query.where(CheckIn.user_id == user_id)
        if gym_id:
            query = query.where(CheckIn.gym_id == gym_id)
        if from_date:
            query = query.where(func.date(CheckIn.checked_in_at) >= from_date)
        if to_date:
            query = query.where(func.date(CheckIn.checked_in_at) <= to_date)

        query = query.order_by(CheckIn.checked_in_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_checkin(
        self,
        user_id: uuid.UUID,
        gym_id: uuid.UUID,
        method: CheckInMethod,
        status: CheckInStatus = CheckInStatus.CONFIRMED,
        approved_by_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> CheckIn:
        """Create a new check-in."""
        checkin = CheckIn(
            user_id=user_id,
            gym_id=gym_id,
            method=method,
            status=status,
            approved_by_id=approved_by_id,
            notes=notes,
        )
        self.db.add(checkin)
        await self.db.commit()
        await self.db.refresh(checkin)
        return checkin

    async def checkout(
        self,
        checkin: CheckIn,
        notes: str | None = None,
    ) -> CheckIn:
        """Check out from a gym."""
        checkin.checked_out_at = datetime.now(timezone.utc)
        if notes:
            checkin.notes = notes

        await self.db.commit()
        await self.db.refresh(checkin)
        return checkin

    # Check-in code operations

    async def get_code_by_value(self, code: str) -> CheckInCode | None:
        """Get a check-in code by its value."""
        result = await self.db.execute(
            select(CheckInCode)
            .where(CheckInCode.code == code.upper())
            .options(selectinload(CheckInCode.gym))
        )
        return result.scalar_one_or_none()

    async def create_code(
        self,
        gym_id: uuid.UUID,
        expires_at: datetime | None = None,
        max_uses: int | None = None,
    ) -> CheckInCode:
        """Create a new check-in code."""
        code = CheckInCode(
            gym_id=gym_id,
            code=secrets.token_hex(4).upper(),  # 8 character hex code
            expires_at=expires_at,
            max_uses=max_uses,
        )
        self.db.add(code)
        await self.db.commit()
        await self.db.refresh(code)
        return code

    async def use_code(self, code: CheckInCode) -> None:
        """Increment code usage count."""
        code.uses_count += 1
        await self.db.commit()

    async def deactivate_code(self, code: CheckInCode) -> None:
        """Deactivate a check-in code."""
        code.is_active = False
        await self.db.commit()

    # Check-in request operations

    async def get_request_by_id(self, request_id: uuid.UUID) -> CheckInRequest | None:
        """Get a check-in request by ID."""
        result = await self.db.execute(
            select(CheckInRequest)
            .where(CheckInRequest.id == request_id)
            .options(selectinload(CheckInRequest.gym))
        )
        return result.scalar_one_or_none()

    async def list_pending_requests(
        self,
        approver_id: uuid.UUID,
        gym_id: uuid.UUID | None = None,
    ) -> list[CheckInRequest]:
        """List pending check-in requests for an approver."""
        query = select(CheckInRequest).where(
            and_(
                CheckInRequest.approver_id == approver_id,
                CheckInRequest.status == CheckInStatus.PENDING,
            )
        ).options(selectinload(CheckInRequest.gym))

        if gym_id:
            query = query.where(CheckInRequest.gym_id == gym_id)

        query = query.order_by(CheckInRequest.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_user_requests(
        self,
        user_id: uuid.UUID,
        status_filter: CheckInStatus | None = None,
        limit: int = 20,
    ) -> list[CheckInRequest]:
        """List check-in requests created by a user (student sees their own requests)."""
        query = select(CheckInRequest).where(
            CheckInRequest.user_id == user_id,
        ).options(
            selectinload(CheckInRequest.gym),
            selectinload(CheckInRequest.approver),
        )

        if status_filter:
            query = query.where(CheckInRequest.status == status_filter)

        query = query.order_by(CheckInRequest.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_request(
        self,
        user_id: uuid.UUID,
        gym_id: uuid.UUID,
        approver_id: uuid.UUID,
        reason: str | None = None,
    ) -> CheckInRequest:
        """Create a check-in request."""
        request = CheckInRequest(
            user_id=user_id,
            gym_id=gym_id,
            approver_id=approver_id,
            reason=reason,
        )
        self.db.add(request)
        await self.db.commit()
        await self.db.refresh(request)
        return request

    async def respond_to_request(
        self,
        request: CheckInRequest,
        approved: bool,
        response_note: str | None = None,
    ) -> tuple[CheckInRequest, CheckIn | None]:
        """Respond to a check-in request."""
        request.status = CheckInStatus.CONFIRMED if approved else CheckInStatus.REJECTED
        request.responded_at = datetime.now(timezone.utc)
        request.response_note = response_note

        checkin = None
        if approved:
            # Create the actual check-in
            checkin = CheckIn(
                user_id=request.user_id,
                gym_id=request.gym_id,
                method=CheckInMethod.REQUEST,
                status=CheckInStatus.CONFIRMED,
                approved_by_id=request.approver_id,
            )
            self.db.add(checkin)

        await self.db.commit()
        await self.db.refresh(request)
        if checkin:
            await self.db.refresh(checkin)

        return request, checkin

    # Location-based check-in

    def calculate_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Calculate distance between two coordinates in meters (Haversine formula)."""
        R = 6371000  # Earth's radius in meters

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    async def find_nearest_gym(
        self,
        latitude: float,
        longitude: float,
        organization_id: uuid.UUID | None = None,
    ) -> tuple[Gym | None, float | None]:
        """Find nearest gym without creating a check-in."""
        gyms = await self.list_gyms(
            organization_id=organization_id,
            active_only=True,
            limit=100,
        )

        nearest_gym = None
        nearest_distance = float('inf')

        for gym in gyms:
            distance = self.calculate_distance(
                latitude, longitude,
                gym.latitude, gym.longitude,
            )
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_gym = gym

        if nearest_gym:
            return nearest_gym, nearest_distance
        return None, None

    async def checkin_by_location(
        self,
        user_id: uuid.UUID,
        latitude: float,
        longitude: float,
        organization_id: uuid.UUID | None = None,
    ) -> tuple[CheckIn | None, Gym | None, float | None]:
        """Check in by location - finds nearest gym within radius."""
        nearest_gym, nearest_distance = await self.find_nearest_gym(
            latitude, longitude, organization_id=organization_id,
        )

        if nearest_gym and nearest_distance is not None and nearest_distance <= nearest_gym.radius_meters:
            checkin = await self.create_checkin(
                user_id=user_id,
                gym_id=nearest_gym.id,
                method=CheckInMethod.LOCATION,
            )
            return checkin, nearest_gym, nearest_distance

        return None, nearest_gym, nearest_distance

    # Trainer location operations

    async def get_trainer_location(
        self,
        trainer_id: uuid.UUID,
    ) -> tuple[float, float, str, uuid.UUID | None, str | None] | None:
        """Get a trainer's current location.

        Priority: active check-in (gym lat/lng) > shared GPS (TrainerLocation).

        Returns:
            Tuple of (latitude, longitude, source, gym_id, gym_name) or None.
            source is "checkin" or "gps".
        """
        # 1. Check active check-in
        active = await self.get_active_checkin(trainer_id)
        if active and active.gym:
            return (
                active.gym.latitude,
                active.gym.longitude,
                "checkin",
                active.gym.id,
                active.gym.name,
            )

        # 2. Check shared GPS location (not expired)
        result = await self.db.execute(
            select(TrainerLocation).where(
                and_(
                    TrainerLocation.user_id == trainer_id,
                    TrainerLocation.expires_at > func.now(),
                )
            )
        )
        loc = result.scalar_one_or_none()
        if loc:
            return (loc.latitude, loc.longitude, "gps", None, None)

        return None

    async def find_nearby_trainers(
        self,
        student_id: uuid.UUID,
        latitude: float,
        longitude: float,
        organization_id: uuid.UUID,
        max_distance_meters: float = 500,
    ) -> list[dict]:
        """Find trainers/coaches near the student's position.

        Looks up all trainers in the organization, gets their location,
        and returns those within max_distance_meters sorted by distance.

        Returns:
            List of dicts: {trainer_id, trainer_name, distance_meters, source, gym_id, gym_name}
        """
        # Get all trainers/coaches in the organization
        result = await self.db.execute(
            select(OrganizationMembership)
            .where(
                and_(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.is_active == True,
                    OrganizationMembership.role.in_([
                        UserRole.TRAINER,
                        UserRole.COACH,
                    ]),
                )
            )
            .options(selectinload(OrganizationMembership.user))
        )
        trainers = result.scalars().all()

        nearby = []
        for trainer_membership in trainers:
            loc = await self.get_trainer_location(trainer_membership.user_id)
            if not loc:
                continue

            t_lat, t_lng, source, gym_id, gym_name = loc
            distance = self.calculate_distance(latitude, longitude, t_lat, t_lng)

            if distance <= max_distance_meters:
                nearby.append({
                    "trainer_id": str(trainer_membership.user_id),
                    "trainer_name": trainer_membership.user.name if trainer_membership.user else "Personal",
                    "distance_meters": round(distance, 1),
                    "source": source,
                    "gym_id": str(gym_id) if gym_id else None,
                    "gym_name": gym_name,
                })

        nearby.sort(key=lambda x: x["distance_meters"])
        return nearby

    async def update_trainer_location(
        self,
        user_id: uuid.UUID,
        latitude: float,
        longitude: float,
        ttl_hours: int = 2,
    ) -> TrainerLocation:
        """Upsert trainer's GPS location with TTL expiry."""
        result = await self.db.execute(
            select(TrainerLocation).where(TrainerLocation.user_id == user_id)
        )
        loc = result.scalar_one_or_none()

        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

        if loc:
            loc.latitude = latitude
            loc.longitude = longitude
            loc.expires_at = expires_at
            loc.updated_at = datetime.now(timezone.utc)
        else:
            loc = TrainerLocation(
                user_id=user_id,
                latitude=latitude,
                longitude=longitude,
                expires_at=expires_at,
            )
            self.db.add(loc)

        await self.db.commit()
        await self.db.refresh(loc)
        return loc

    # Stats

    async def get_user_checkin_stats(
        self,
        user_id: uuid.UUID,
        days: int = 30,
    ) -> dict:
        """Get check-in statistics for a user."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        checkins = await self.list_checkins(
            user_id=user_id,
            from_date=cutoff_date.date(),
            limit=1000,
        )

        total_duration = 0
        for checkin in checkins:
            if checkin.duration_minutes:
                total_duration += checkin.duration_minutes

        return {
            "period_days": days,
            "total_checkins": len(checkins),
            "total_duration_minutes": total_duration,
            "avg_duration_minutes": total_duration / len(checkins) if checkins else 0,
        }
