"""Consultancy marketplace router."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.users.models import User

from .models import (
    ConsultancyCategory,
    ConsultancyFormat,
    ConsultancyListing,
    ConsultancyReview,
    ConsultancyTransaction,
    ProfessionalProfile,
    TransactionStatus,
)
from .schemas import (
    ConsultancyCheckoutResponse,
    ConsultancyListingCreate,
    ConsultancyListingListResponse,
    ConsultancyListingResponse,
    ConsultancyListingUpdate,
    ConsultancyPurchaseRequest,
    ConsultancyReviewCreate,
    ConsultancyReviewResponse,
    ConsultancyTransactionListResponse,
    ConsultancyTransactionResponse,
    ProfessionalProfileCreate,
    ProfessionalProfileResponse,
    ProfessionalProfileUpdate,
)

router = APIRouter(tags=["consultancy"])


# --- Helper functions ---


def _profile_to_response(profile: ProfessionalProfile) -> ProfessionalProfileResponse:
    return ProfessionalProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        user_name=profile.user.name if profile.user else "Unknown",
        user_avatar_url=profile.user.avatar_url if profile.user else None,
        headline=profile.headline,
        bio=profile.bio,
        specialties=profile.specialties,
        certifications=profile.certifications,
        languages=profile.languages,
        experience_years=profile.experience_years,
        city=profile.city,
        state=profile.state,
        country=profile.country,
        instagram=profile.instagram,
        website=profile.website,
        rating_average=profile.rating_average,
        rating_count=profile.rating_count,
        total_students_served=profile.total_students_served,
        total_consultancies_sold=profile.total_consultancies_sold,
        is_public=profile.is_public,
        is_verified=profile.is_verified,
        is_featured=profile.is_featured,
        is_accepting_students=profile.is_accepting_students,
        created_at=profile.created_at,
    )


def _listing_to_response(listing: ConsultancyListing) -> ConsultancyListingResponse:
    # Get professional info from the relationship
    prof = listing.professional
    user = prof.user if prof else None

    return ConsultancyListingResponse(
        id=listing.id,
        professional_id=listing.professional_id,
        professional_name=user.name if user else "Unknown",
        professional_avatar_url=user.avatar_url if user else None,
        professional_headline=prof.headline if prof else None,
        professional_rating=prof.rating_average if prof else None,
        title=listing.title,
        short_description=listing.short_description,
        full_description=listing.full_description,
        cover_image_url=listing.cover_image_url,
        category=listing.category,
        tags=listing.tags,
        format=listing.format,
        price_cents=listing.price_cents,
        currency=listing.currency,
        duration_days=listing.duration_days,
        sessions_included=listing.sessions_included,
        includes=listing.includes,
        commission_rate=listing.commission_rate,
        purchase_count=listing.purchase_count,
        rating_average=listing.rating_average,
        rating_count=listing.rating_count,
        view_count=listing.view_count,
        is_active=listing.is_active,
        is_featured=listing.is_featured,
        created_at=listing.created_at,
    )


def _transaction_to_response(txn: ConsultancyTransaction) -> ConsultancyTransactionResponse:
    return ConsultancyTransactionResponse(
        id=txn.id,
        listing_id=txn.listing_id,
        listing_title=txn.listing.title if txn.listing else "Unknown",
        buyer_id=txn.buyer_id,
        buyer_name=txn.buyer.name if txn.buyer else "Unknown",
        seller_id=txn.seller_id,
        seller_name=txn.seller.name if txn.seller else "Unknown",
        amount_cents=txn.amount_cents,
        commission_cents=txn.commission_cents,
        seller_earnings_cents=txn.seller_earnings_cents,
        currency=txn.currency,
        status=txn.status,
        confirmed_at=txn.confirmed_at,
        started_at=txn.started_at,
        completed_at=txn.completed_at,
        expires_at=txn.expires_at,
        buyer_notes=txn.buyer_notes,
        created_at=txn.created_at,
    )


# --- Professional Profiles ---


@router.get("/profiles", response_model=list[ProfessionalProfileResponse])
async def list_professional_profiles(
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Annotated[str | None, Query()] = None,
    city: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    accepting_only: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProfessionalProfileResponse]:
    """Browse professional profiles on the marketplace."""
    base_filter = [
        ProfessionalProfile.is_public == True,  # noqa: E712
    ]

    if accepting_only:
        base_filter.append(ProfessionalProfile.is_accepting_students == True)  # noqa: E712

    if city:
        base_filter.append(ProfessionalProfile.city.ilike(f"%{city}%"))

    query = (
        select(ProfessionalProfile)
        .where(and_(*base_filter))
        .order_by(
            ProfessionalProfile.is_featured.desc(),
            ProfessionalProfile.rating_average.desc().nullslast(),
            ProfessionalProfile.total_consultancies_sold.desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    profiles = list(result.scalars().all())

    return [_profile_to_response(p) for p in profiles]


@router.get("/profiles/me", response_model=ProfessionalProfileResponse)
async def get_my_profile(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProfessionalProfileResponse:
    """Get or create the current user's professional profile."""
    query = select(ProfessionalProfile).where(
        ProfessionalProfile.user_id == current_user.id
    )
    result = await db.execute(query)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Professional profile not found. Create one first.",
        )

    return _profile_to_response(profile)


@router.post("/profiles", response_model=ProfessionalProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    request: ProfessionalProfileCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProfessionalProfileResponse:
    """Create a professional profile for the marketplace."""
    # Check if profile already exists
    existing = await db.execute(
        select(ProfessionalProfile).where(ProfessionalProfile.user_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Professional profile already exists",
        )

    profile = ProfessionalProfile(
        user_id=current_user.id,
        **request.model_dump(),
    )

    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    # Reload with relationships
    query = select(ProfessionalProfile).where(ProfessionalProfile.id == profile.id)
    result = await db.execute(query)
    profile = result.scalar_one()

    return _profile_to_response(profile)


@router.put("/profiles/me", response_model=ProfessionalProfileResponse)
async def update_profile(
    request: ProfessionalProfileUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProfessionalProfileResponse:
    """Update the current user's professional profile."""
    query = select(ProfessionalProfile).where(
        ProfessionalProfile.user_id == current_user.id
    )
    result = await db.execute(query)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Professional profile not found",
        )

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    return _profile_to_response(profile)


@router.get("/profiles/{user_id}", response_model=ProfessionalProfileResponse)
async def get_profile(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProfessionalProfileResponse:
    """Get a specific professional's public profile."""
    query = select(ProfessionalProfile).where(
        ProfessionalProfile.user_id == user_id,
        ProfessionalProfile.is_public == True,  # noqa: E712
    )
    result = await db.execute(query)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Professional profile not found",
        )

    return _profile_to_response(profile)


# --- Consultancy Listings ---


@router.get("/listings", response_model=ConsultancyListingListResponse)
async def list_consultancies(
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Annotated[ConsultancyCategory | None, Query()] = None,
    format: Annotated[ConsultancyFormat | None, Query()] = None,
    min_price: Annotated[int | None, Query(ge=0)] = None,
    max_price: Annotated[int | None, Query(ge=0)] = None,
    search: Annotated[str | None, Query()] = None,
    sort: Annotated[str, Query()] = "featured",  # featured, price_asc, price_desc, rating, newest
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConsultancyListingListResponse:
    """Browse consultancy listings on the marketplace."""
    base_filter = [
        ConsultancyListing.is_active == True,  # noqa: E712
        ConsultancyListing.deleted_at.is_(None),
    ]

    if category:
        base_filter.append(ConsultancyListing.category == category)
    if format:
        base_filter.append(ConsultancyListing.format == format)
    if min_price is not None:
        base_filter.append(ConsultancyListing.price_cents >= min_price)
    if max_price is not None:
        base_filter.append(ConsultancyListing.price_cents <= max_price)
    if search:
        base_filter.append(
            ConsultancyListing.title.ilike(f"%{search}%")
            | ConsultancyListing.short_description.ilike(f"%{search}%")
        )

    # Count
    count_query = select(func.count(ConsultancyListing.id)).where(and_(*base_filter))
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Sort
    order_by = ConsultancyListing.is_featured.desc()
    if sort == "price_asc":
        order_by = ConsultancyListing.price_cents.asc()
    elif sort == "price_desc":
        order_by = ConsultancyListing.price_cents.desc()
    elif sort == "rating":
        order_by = ConsultancyListing.rating_average.desc().nullslast()
    elif sort == "newest":
        order_by = ConsultancyListing.created_at.desc()

    query = (
        select(ConsultancyListing)
        .where(and_(*base_filter))
        .order_by(order_by)
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    listings = list(result.scalars().all())

    return ConsultancyListingListResponse(
        listings=[_listing_to_response(l) for l in listings],
        total=total,
    )


@router.get("/listings/mine", response_model=ConsultancyListingListResponse)
async def list_my_consultancies(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_inactive: Annotated[bool, Query()] = False,
) -> ConsultancyListingListResponse:
    """List current user's own consultancy listings."""
    base_filter = [
        ConsultancyListing.professional_id == current_user.id,
        ConsultancyListing.deleted_at.is_(None),
    ]

    if not include_inactive:
        base_filter.append(ConsultancyListing.is_active == True)  # noqa: E712

    count_query = select(func.count(ConsultancyListing.id)).where(and_(*base_filter))
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    query = (
        select(ConsultancyListing)
        .where(and_(*base_filter))
        .order_by(ConsultancyListing.created_at.desc())
    )

    result = await db.execute(query)
    listings = list(result.scalars().all())

    return ConsultancyListingListResponse(
        listings=[_listing_to_response(l) for l in listings],
        total=total,
    )


@router.post("/listings", response_model=ConsultancyListingResponse, status_code=status.HTTP_201_CREATED)
async def create_listing(
    request: ConsultancyListingCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsultancyListingResponse:
    """Create a new consultancy listing."""
    # Ensure professional has a profile
    prof_query = select(ProfessionalProfile).where(
        ProfessionalProfile.user_id == current_user.id
    )
    prof_result = await db.execute(prof_query)
    profile = prof_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create a professional profile first before listing consultancies",
        )

    listing = ConsultancyListing(
        professional_id=profile.id,
        commission_rate=0,  # 0% during launch phase
        **request.model_dump(),
    )

    db.add(listing)
    await db.commit()
    await db.refresh(listing)

    # Reload with relationships
    query = select(ConsultancyListing).where(ConsultancyListing.id == listing.id)
    result = await db.execute(query)
    listing = result.scalar_one()

    return _listing_to_response(listing)


@router.get("/listings/{listing_id}", response_model=ConsultancyListingResponse)
async def get_listing(
    listing_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsultancyListingResponse:
    """Get a specific consultancy listing."""
    listing = await db.get(ConsultancyListing, listing_id)

    if not listing or listing.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    # Increment view count
    listing.view_count += 1
    await db.commit()

    return _listing_to_response(listing)


@router.put("/listings/{listing_id}", response_model=ConsultancyListingResponse)
async def update_listing(
    listing_id: UUID,
    request: ConsultancyListingUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsultancyListingResponse:
    """Update a consultancy listing (owner only)."""
    listing = await db.get(ConsultancyListing, listing_id)

    if not listing or listing.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    if listing.professional_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can update this listing",
        )

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(listing, field, value)

    await db.commit()
    await db.refresh(listing)

    return _listing_to_response(listing)


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing(
    listing_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Soft-delete a consultancy listing (owner only)."""
    from datetime import datetime, timezone

    listing = await db.get(ConsultancyListing, listing_id)

    if not listing or listing.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    if listing.professional_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can delete this listing",
        )

    listing.deleted_at = datetime.now(timezone.utc)
    listing.is_active = False
    await db.commit()


# --- Transactions ---


@router.post("/purchase", response_model=ConsultancyCheckoutResponse, status_code=status.HTTP_201_CREATED)
async def purchase_consultancy(
    request: ConsultancyPurchaseRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsultancyCheckoutResponse:
    """Purchase a consultancy service with PIX checkout."""
    listing = await db.get(ConsultancyListing, request.listing_id)

    if not listing or not listing.is_active or listing.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found or not available",
        )

    # Can't buy your own listing
    if listing.professional_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot purchase your own consultancy",
        )

    commission_cents = listing.commission_amount_cents
    seller_earnings = listing.professional_earnings_cents

    txn = ConsultancyTransaction(
        listing_id=listing.id,
        buyer_id=current_user.id,
        seller_id=listing.professional_id,
        amount_cents=listing.price_cents,
        commission_cents=commission_cents,
        seller_earnings_cents=seller_earnings,
        currency=listing.currency,
        status=TransactionStatus.PENDING,
        payment_provider=request.payment_provider,
        buyer_notes=request.buyer_notes,
    )

    db.add(txn)

    # Update listing stats
    listing.purchase_count += 1

    await db.commit()
    await db.refresh(txn)

    # Reload with relationships
    query = select(ConsultancyTransaction).where(ConsultancyTransaction.id == txn.id)
    result = await db.execute(query)
    txn = result.scalar_one()

    # Generate PIX data if payment_provider is pix
    pix_copy_paste = None
    pix_qr_code = None
    if request.payment_provider == "pix":
        pix_copy_paste = (
            f"00020126580014br.gov.bcb.pix0136{txn.id}"
            f"5204000053039865802BR5925{listing.title[:25]}"
            f"6009SAO PAULO62070503***6304"
        )
        pix_qr_code = pix_copy_paste

    base = _transaction_to_response(txn)
    return ConsultancyCheckoutResponse(
        **base.model_dump(),
        pix_qr_code=pix_qr_code,
        pix_copy_paste=pix_copy_paste,
    )


@router.get("/transactions/{transaction_id}/status")
async def get_transaction_status(
    transaction_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get transaction payment status (for polling)."""
    txn = await db.get(ConsultancyTransaction, transaction_id)

    if not txn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    if txn.buyer_id != current_user.id and txn.seller_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this transaction",
        )

    return {
        "status": txn.status.value,
        "transaction_id": str(txn.id),
    }


@router.get("/transactions", response_model=ConsultancyTransactionListResponse)
async def list_transactions(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    as_seller: Annotated[bool, Query()] = False,
    status_filter: Annotated[TransactionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConsultancyTransactionListResponse:
    """List consultancy transactions."""
    if as_seller:
        base_filter = [ConsultancyTransaction.seller_id == current_user.id]
    else:
        base_filter = [ConsultancyTransaction.buyer_id == current_user.id]

    if status_filter:
        base_filter.append(ConsultancyTransaction.status == status_filter)

    count_query = select(func.count(ConsultancyTransaction.id)).where(and_(*base_filter))
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    query = (
        select(ConsultancyTransaction)
        .where(and_(*base_filter))
        .order_by(ConsultancyTransaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    transactions = list(result.scalars().all())

    return ConsultancyTransactionListResponse(
        transactions=[_transaction_to_response(t) for t in transactions],
        total=total,
    )


@router.post("/transactions/{transaction_id}/confirm", response_model=ConsultancyTransactionResponse)
async def confirm_transaction(
    transaction_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsultancyTransactionResponse:
    """Confirm a transaction (payment received). Seller action."""
    from datetime import datetime, timezone

    txn = await db.get(ConsultancyTransaction, transaction_id)

    if not txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    if txn.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the seller can confirm")

    if txn.status != TransactionStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transaction is not in pending state")

    txn.status = TransactionStatus.CONFIRMED
    txn.confirmed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(txn)

    return _transaction_to_response(txn)


@router.post("/transactions/{transaction_id}/complete", response_model=ConsultancyTransactionResponse)
async def complete_transaction(
    transaction_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsultancyTransactionResponse:
    """Mark a transaction as completed. Seller action."""
    from datetime import datetime, timezone

    txn = await db.get(ConsultancyTransaction, transaction_id)

    if not txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    if txn.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the seller can complete")

    if txn.status not in (TransactionStatus.CONFIRMED, TransactionStatus.ACTIVE):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transaction cannot be completed from current state")

    txn.status = TransactionStatus.COMPLETED
    txn.completed_at = datetime.now(timezone.utc)

    # Update professional profile stats
    prof_query = select(ProfessionalProfile).where(
        ProfessionalProfile.user_id == txn.seller_id
    )
    prof_result = await db.execute(prof_query)
    profile = prof_result.scalar_one_or_none()
    if profile:
        profile.total_consultancies_sold += 1

    await db.commit()
    await db.refresh(txn)

    return _transaction_to_response(txn)


# --- Reviews ---


@router.post("/transactions/{transaction_id}/review", response_model=ConsultancyReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(
    transaction_id: UUID,
    request: ConsultancyReviewCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsultancyReviewResponse:
    """Leave a review for a completed consultancy."""
    txn = await db.get(ConsultancyTransaction, transaction_id)

    if not txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    if txn.buyer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the buyer can review")

    if txn.status != TransactionStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only review completed transactions")

    # Check if already reviewed
    existing = await db.execute(
        select(ConsultancyReview).where(ConsultancyReview.transaction_id == transaction_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transaction already reviewed")

    review = ConsultancyReview(
        transaction_id=txn.id,
        listing_id=txn.listing_id,
        reviewer_id=current_user.id,
        professional_id=txn.seller_id,
        rating=request.rating,
        title=request.title,
        comment=request.comment,
    )

    db.add(review)

    # Update listing rating
    listing = await db.get(ConsultancyListing, txn.listing_id)
    if listing:
        # Recalculate average
        reviews_query = select(func.avg(ConsultancyReview.rating), func.count(ConsultancyReview.id)).where(
            ConsultancyReview.listing_id == txn.listing_id
        )
        reviews_result = await db.execute(reviews_query)
        avg_rating, count = reviews_result.one()
        listing.rating_average = avg_rating
        listing.rating_count = (count or 0) + 1  # +1 for new review not yet committed

    # Update professional profile rating
    prof_query = select(ProfessionalProfile).where(
        ProfessionalProfile.user_id == txn.seller_id
    )
    prof_result = await db.execute(prof_query)
    profile = prof_result.scalar_one_or_none()
    if profile:
        all_reviews_query = select(func.avg(ConsultancyReview.rating), func.count(ConsultancyReview.id)).where(
            ConsultancyReview.professional_id == txn.seller_id
        )
        all_reviews_result = await db.execute(all_reviews_query)
        avg_all, count_all = all_reviews_result.one()
        profile.rating_average = avg_all
        profile.rating_count = (count_all or 0) + 1

    await db.commit()
    await db.refresh(review)

    return ConsultancyReviewResponse(
        id=review.id,
        transaction_id=review.transaction_id,
        listing_id=review.listing_id,
        reviewer_id=review.reviewer_id,
        reviewer_name=current_user.name,
        reviewer_avatar_url=current_user.avatar_url,
        professional_id=review.professional_id,
        rating=review.rating,
        title=review.title,
        comment=review.comment,
        response=review.response,
        responded_at=review.responded_at,
        is_verified_purchase=review.is_verified_purchase,
        created_at=review.created_at,
    )


@router.get("/listings/{listing_id}/reviews", response_model=list[ConsultancyReviewResponse])
async def list_listing_reviews(
    listing_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConsultancyReviewResponse]:
    """Get reviews for a specific listing."""
    query = (
        select(ConsultancyReview)
        .where(ConsultancyReview.listing_id == listing_id)
        .order_by(ConsultancyReview.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    reviews = list(result.scalars().all())

    return [
        ConsultancyReviewResponse(
            id=r.id,
            transaction_id=r.transaction_id,
            listing_id=r.listing_id,
            reviewer_id=r.reviewer_id,
            reviewer_name=r.reviewer.name if r.reviewer else "Unknown",
            reviewer_avatar_url=r.reviewer.avatar_url if r.reviewer else None,
            professional_id=r.professional_id,
            rating=r.rating,
            title=r.title,
            comment=r.comment,
            response=r.response,
            responded_at=r.responded_at,
            is_verified_purchase=r.is_verified_purchase,
            created_at=r.created_at,
        )
        for r in reviews
    ]
