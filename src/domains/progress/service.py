"""Progress service with database operations."""
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.progress.models import (
    MeasurementLog,
    PhotoAngle,
    ProgressPhoto,
    WeightGoal,
    WeightLog,
)


class ProgressService:
    """Service for handling progress tracking operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # Weight operations

    async def get_weight_log_by_id(
        self,
        log_id: uuid.UUID,
    ) -> WeightLog | None:
        """Get a weight log by ID."""
        result = await self.db.execute(
            select(WeightLog).where(WeightLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def list_weight_logs(
        self,
        user_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WeightLog]:
        """List weight logs for a user."""
        query = select(WeightLog).where(WeightLog.user_id == user_id)

        if from_date:
            query = query.where(
                func.date(WeightLog.logged_at) >= from_date
            )
        if to_date:
            query = query.where(
                func.date(WeightLog.logged_at) <= to_date
            )

        query = query.order_by(WeightLog.logged_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_weight_log(
        self,
        user_id: uuid.UUID,
        weight_kg: float,
        logged_at: datetime | None = None,
        notes: str | None = None,
    ) -> WeightLog:
        """Create a new weight log."""
        log = WeightLog(
            user_id=user_id,
            weight_kg=weight_kg,
            logged_at=logged_at or datetime.utcnow(),
            notes=notes,
        )
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def update_weight_log(
        self,
        log: WeightLog,
        weight_kg: float | None = None,
        logged_at: datetime | None = None,
        notes: str | None = None,
    ) -> WeightLog:
        """Update a weight log."""
        if weight_kg is not None:
            log.weight_kg = weight_kg
        if logged_at is not None:
            log.logged_at = logged_at
        if notes is not None:
            log.notes = notes

        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def delete_weight_log(self, log: WeightLog) -> None:
        """Delete a weight log."""
        await self.db.delete(log)
        await self.db.commit()

    async def get_latest_weight(self, user_id: uuid.UUID) -> WeightLog | None:
        """Get user's most recent weight log."""
        result = await self.db.execute(
            select(WeightLog)
            .where(WeightLog.user_id == user_id)
            .order_by(WeightLog.logged_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # Measurement operations

    async def get_measurement_log_by_id(
        self,
        log_id: uuid.UUID,
    ) -> MeasurementLog | None:
        """Get a measurement log by ID."""
        result = await self.db.execute(
            select(MeasurementLog).where(MeasurementLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def list_measurement_logs(
        self,
        user_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MeasurementLog]:
        """List measurement logs for a user."""
        query = select(MeasurementLog).where(MeasurementLog.user_id == user_id)

        if from_date:
            query = query.where(
                func.date(MeasurementLog.logged_at) >= from_date
            )
        if to_date:
            query = query.where(
                func.date(MeasurementLog.logged_at) <= to_date
            )

        query = query.order_by(MeasurementLog.logged_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_measurement_log(
        self,
        user_id: uuid.UUID,
        logged_at: datetime | None = None,
        chest_cm: float | None = None,
        waist_cm: float | None = None,
        hips_cm: float | None = None,
        biceps_cm: float | None = None,
        thigh_cm: float | None = None,
        calf_cm: float | None = None,
        neck_cm: float | None = None,
        forearm_cm: float | None = None,
        notes: str | None = None,
    ) -> MeasurementLog:
        """Create a new measurement log."""
        log = MeasurementLog(
            user_id=user_id,
            logged_at=logged_at or datetime.utcnow(),
            chest_cm=chest_cm,
            waist_cm=waist_cm,
            hips_cm=hips_cm,
            biceps_cm=biceps_cm,
            thigh_cm=thigh_cm,
            calf_cm=calf_cm,
            neck_cm=neck_cm,
            forearm_cm=forearm_cm,
            notes=notes,
        )
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def update_measurement_log(
        self,
        log: MeasurementLog,
        chest_cm: float | None = None,
        waist_cm: float | None = None,
        hips_cm: float | None = None,
        biceps_cm: float | None = None,
        thigh_cm: float | None = None,
        calf_cm: float | None = None,
        neck_cm: float | None = None,
        forearm_cm: float | None = None,
        notes: str | None = None,
    ) -> MeasurementLog:
        """Update a measurement log."""
        if chest_cm is not None:
            log.chest_cm = chest_cm
        if waist_cm is not None:
            log.waist_cm = waist_cm
        if hips_cm is not None:
            log.hips_cm = hips_cm
        if biceps_cm is not None:
            log.biceps_cm = biceps_cm
        if thigh_cm is not None:
            log.thigh_cm = thigh_cm
        if calf_cm is not None:
            log.calf_cm = calf_cm
        if neck_cm is not None:
            log.neck_cm = neck_cm
        if forearm_cm is not None:
            log.forearm_cm = forearm_cm
        if notes is not None:
            log.notes = notes

        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def delete_measurement_log(self, log: MeasurementLog) -> None:
        """Delete a measurement log."""
        await self.db.delete(log)
        await self.db.commit()

    async def get_latest_measurements(
        self,
        user_id: uuid.UUID,
    ) -> MeasurementLog | None:
        """Get user's most recent measurement log."""
        result = await self.db.execute(
            select(MeasurementLog)
            .where(MeasurementLog.user_id == user_id)
            .order_by(MeasurementLog.logged_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # Photo operations

    async def get_photo_by_id(
        self,
        photo_id: uuid.UUID,
    ) -> ProgressPhoto | None:
        """Get a progress photo by ID."""
        result = await self.db.execute(
            select(ProgressPhoto).where(ProgressPhoto.id == photo_id)
        )
        return result.scalar_one_or_none()

    async def list_photos(
        self,
        user_id: uuid.UUID,
        angle: PhotoAngle | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ProgressPhoto]:
        """List progress photos for a user."""
        query = select(ProgressPhoto).where(ProgressPhoto.user_id == user_id)

        if angle:
            query = query.where(ProgressPhoto.angle == angle)
        if from_date:
            query = query.where(
                func.date(ProgressPhoto.logged_at) >= from_date
            )
        if to_date:
            query = query.where(
                func.date(ProgressPhoto.logged_at) <= to_date
            )

        query = query.order_by(ProgressPhoto.logged_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_photo(
        self,
        user_id: uuid.UUID,
        photo_url: str,
        angle: PhotoAngle,
        thumbnail_url: str | None = None,
        logged_at: datetime | None = None,
        notes: str | None = None,
        weight_log_id: uuid.UUID | None = None,
        measurement_log_id: uuid.UUID | None = None,
    ) -> ProgressPhoto:
        """Create a new progress photo."""
        photo = ProgressPhoto(
            user_id=user_id,
            photo_url=photo_url,
            thumbnail_url=thumbnail_url,
            angle=angle,
            logged_at=logged_at or datetime.utcnow(),
            notes=notes,
            weight_log_id=weight_log_id,
            measurement_log_id=measurement_log_id,
        )
        self.db.add(photo)
        await self.db.commit()
        await self.db.refresh(photo)
        return photo

    async def delete_photo(self, photo: ProgressPhoto) -> None:
        """Delete a progress photo."""
        await self.db.delete(photo)
        await self.db.commit()

    # Weight goal operations

    async def get_weight_goal(self, user_id: uuid.UUID) -> WeightGoal | None:
        """Get user's weight goal."""
        result = await self.db.execute(
            select(WeightGoal).where(WeightGoal.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_or_update_weight_goal(
        self,
        user_id: uuid.UUID,
        target_weight_kg: float,
        start_weight_kg: float,
        target_date: datetime | None = None,
        notes: str | None = None,
    ) -> WeightGoal:
        """Create or update user's weight goal."""
        goal = await self.get_weight_goal(user_id)

        if goal:
            goal.target_weight_kg = target_weight_kg
            goal.target_date = target_date
            if notes is not None:
                goal.notes = notes
        else:
            goal = WeightGoal(
                user_id=user_id,
                target_weight_kg=target_weight_kg,
                start_weight_kg=start_weight_kg,
                target_date=target_date,
                notes=notes,
            )
            self.db.add(goal)

        await self.db.commit()
        await self.db.refresh(goal)
        return goal

    async def delete_weight_goal(self, goal: WeightGoal) -> None:
        """Delete weight goal."""
        await self.db.delete(goal)
        await self.db.commit()

    # Stats operations

    async def get_progress_stats(
        self,
        user_id: uuid.UUID,
        days: int = 30,
    ) -> dict:
        """Get progress statistics for a user."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get weight stats
        weight_logs = await self.list_weight_logs(
            user_id=user_id,
            from_date=cutoff_date.date(),
            limit=1000,
        )

        # Get measurement stats
        measurement_logs = await self.list_measurement_logs(
            user_id=user_id,
            from_date=cutoff_date.date(),
            limit=1000,
        )

        # Get weight goal
        goal = await self.get_weight_goal(user_id)

        # Calculate stats
        weight_change = 0.0
        if len(weight_logs) >= 2:
            weight_change = weight_logs[0].weight_kg - weight_logs[-1].weight_kg

        latest_weight = weight_logs[0].weight_kg if weight_logs else None
        starting_weight = weight_logs[-1].weight_kg if weight_logs else None

        # Calculate goal progress
        goal_progress = None
        if goal and latest_weight:
            total_to_lose = goal.start_weight_kg - goal.target_weight_kg
            lost_so_far = goal.start_weight_kg - latest_weight
            if total_to_lose != 0:
                goal_progress = (lost_so_far / total_to_lose) * 100

        return {
            "period_days": days,
            "weight_logs_count": len(weight_logs),
            "measurement_logs_count": len(measurement_logs),
            "latest_weight_kg": latest_weight,
            "starting_weight_kg": starting_weight,
            "weight_change_kg": weight_change,
            "goal_weight_kg": goal.target_weight_kg if goal else None,
            "goal_progress_percent": goal_progress,
        }
