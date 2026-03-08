# Error Handling Guide for Developers

## Overview

This guide explains the error handling patterns used in SomaAI and how to implement them correctly when adding new endpoints or modifying existing ones.

## Error Handling Layers

SomaAI uses a **defense-in-depth** approach with error handling at multiple layers:

```
┌─────────────────────────────────────────┐
│  1. API Endpoint Layer                  │  ← Catches service exceptions
│     (src/somaai/api/v1/endpoints/)      │     Translates to HTTP responses
├─────────────────────────────────────────┤
│  2. Service Layer                       │  ← Business logic validation
│     (src/somaai/modules/*/service.py)   │     Raises domain exceptions
├─────────────────────────────────────────┤
│  3. CRUD Layer                          │  ← Database operations
│     (src/somaai/db/crud.py)             │     Catches IntegrityError
├─────────────────────────────────────────┤
│  4. Global Exception Handler            │  ← Safety net for missed errors
│     (src/somaai/middleware/error_handler.py)
└─────────────────────────────────────────┘
```

## Domain Exceptions

Use these custom exceptions from `somaai.exceptions`:

| Exception | HTTP Status | Use Case |
|-----------|-------------|----------|
| `ConflictError` | 409 | Duplicate resources, concurrent modification |
| `NotFoundError` | 404 | Resource doesn't exist |
| `ValidationError` | 400 | Invalid input data |
| `ServiceUnavailableError` | 503 | External service down (Redis, Qdrant, LLM) |
| `RAGError` | 201* | RAG pipeline failure (graceful degradation) |

*RAGError is special - it triggers graceful degradation, not an error response.

## Implementation Patterns

### Pattern 1: CRUD Layer (Database Operations)

**When to use:** Any database create/update operation that might violate constraints.

```python
async def create_resource(db: AsyncSession, data: dict) -> Resource:
    """Create a new resource.
    
    Raises:
        ConflictError: If resource with same ID already exists
    """
    from sqlalchemy.exc import IntegrityError
    from somaai.exceptions import ConflictError
    
    resource = Resource(**data)
    db.add(resource)
    
    try:
        await db.commit()
        await db.refresh(resource)
        return resource
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e).lower()
        
        # Duplicate key
        if "duplicate key" in error_msg or "unique constraint" in error_msg:
            raise ConflictError(f"Resource with ID '{data.get('id')}' already exists")
        
        # Foreign key violation
        if "foreign key" in error_msg:
            raise ValidationError("Invalid reference. Related resource does not exist.")
        
        # NOT NULL violation
        if "not null" in error_msg or "null value" in error_msg:
            raise ValidationError("Missing required field.")
        
        # Unknown integrity error - let global handler deal with it
        raise
```

**Key points:**
- Always rollback on IntegrityError
- Translate database errors to domain exceptions
- Include helpful context in error messages
- Re-raise unknown errors for global handler

### Pattern 2: Service Layer (Business Logic)

**When to use:** Business logic validation, orchestration of multiple operations.

```python
async def create_resource(self, data: ResourceCreate) -> ResourceResponse:
    """Create a new resource.
    
    Raises:
        ConflictError: If resource already exists
        ValidationError: If data is invalid
    """
    # Business logic validation
    if not await self._is_valid(data):
        raise ValidationError("Invalid resource data")
    
    # Check for duplicates (if not handled by DB constraint)
    existing = await self._find_by_name(data.name)
    if existing:
        raise ConflictError(f"Resource '{data.name}' already exists")
    
    # Delegate to CRUD layer (which may also raise ConflictError)
    resource = await crud.create_resource(self.db, data.model_dump())
    
    # Post-creation logic
    await self._invalidate_cache()
    
    return ResourceResponse.from_orm(resource)
```

**Key points:**
- Document exceptions in docstring
- Validate business rules before database operations
- Let CRUD layer exceptions bubble up
- Don't catch exceptions you can't handle

### Pattern 3: API Endpoint Layer (HTTP Interface)

**When to use:** All API endpoints that call service methods.

```python
@router.post("/resources", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    data: ResourceCreate,
    service: ResourceService = Depends(get_service),
):
    """Create a new resource."""
    from somaai.exceptions import ConflictError, ValidationError, conflict_exception, bad_request_exception
    
    try:
        return await service.create_resource(data)
    except ConflictError as e:
        raise conflict_exception(detail=str(e))
    except ValidationError as e:
        raise bad_request_exception(detail=str(e))
```

**Key points:**
- Use helper functions (`conflict_exception`, `bad_request_exception`, etc.)
- Only catch exceptions you expect from the service
- Let unexpected exceptions reach global handler
- Keep endpoint logic minimal

### Pattern 4: Global Handler (Safety Net)

The global exception handler in `src/somaai/middleware/error_handler.py` catches:

- Unhandled `IntegrityError` → 409 or 400 depending on type
- Unhandled `ConflictError` → 409
- Unhandled `NotFoundError` → 404
- Unhandled `ValidationError` → 400
- Unhandled `ServiceUnavailableError` → 503
- Any other `Exception` → 500 with generic message

**You don't need to modify this** - it's a safety net.

## Error Response Format

All errors return this structure:

```json
{
  "detail": "Human-readable error message",
  "error_type": "conflict"
}
```

Error types:
- `conflict` - 409
- `validation_error` - 400
- `not_found` - 404
- `service_unavailable` - 503
- `internal_error` - 500

## Common Scenarios

### Scenario 1: Creating a Resource with Unique Constraint

```python
# CRUD Layer
async def create_user(db: AsyncSession, data: dict) -> User:
    from sqlalchemy.exc import IntegrityError
    from somaai.exceptions import ConflictError
    
    user = User(**data)
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
        return user
    except IntegrityError as e:
        await db.rollback()
        if "duplicate key" in str(e).lower():
            raise ConflictError(f"User with email '{data.get('email')}' already exists")
        raise

# Service Layer
async def create_user(self, data: UserCreate) -> UserResponse:
    """Create user. Raises ConflictError if email exists."""
    user = await crud.create_user(self.db, data.model_dump())
    return UserResponse.from_orm(user)

# Endpoint Layer
@router.post("/users", status_code=201)
async def create_user(data: UserCreate, service: UserService = Depends(get_service)):
    from somaai.exceptions import ConflictError, conflict_exception
    try:
        return await service.create_user(data)
    except ConflictError as e:
        raise conflict_exception(detail=str(e))
```

### Scenario 2: Updating a Resource (Not Found)

```python
# CRUD Layer
async def update_user(db: AsyncSession, user_id: str, data: dict) -> User | None:
    user = await db.get(User, user_id)
    if not user:
        return None
    for key, value in data.items():
        setattr(user, key, value)
    await db.commit()
    return user

# Service Layer
async def update_user(self, user_id: str, data: UserUpdate) -> UserResponse:
    """Update user. Raises NotFoundError if not found."""
    from somaai.exceptions import NotFoundError
    
    user = await crud.update_user(self.db, user_id, data.model_dump(exclude_unset=True))
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    return UserResponse.from_orm(user)

# Endpoint Layer
@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    data: UserUpdate,
    service: UserService = Depends(get_service),
):
    from somaai.exceptions import NotFoundError, not_found_exception
    try:
        return await service.update_user(user_id, data)
    except NotFoundError as e:
        raise not_found_exception(detail=str(e))
```

### Scenario 3: External Service Failure

```python
# Service Layer
async def get_embeddings(self, text: str) -> list[float]:
    """Get embeddings. Raises ServiceUnavailableError if service down."""
    from somaai.exceptions import ServiceUnavailableError
    
    try:
        return await self.embedding_client.embed(text)
    except ConnectionError as e:
        raise ServiceUnavailableError("Embedding service unavailable")

# Endpoint Layer
@router.post("/embed")
async def embed_text(text: str, service: EmbedService = Depends(get_service)):
    from somaai.exceptions import ServiceUnavailableError, service_unavailable_exception
    try:
        return await service.get_embeddings(text)
    except ServiceUnavailableError as e:
        raise service_unavailable_exception(detail=str(e))
```

## Testing Error Handling

### Unit Tests

```python
import pytest
from somaai.exceptions import ConflictError

async def test_create_duplicate_user(db_session):
    """Test that creating duplicate user raises ConflictError."""
    service = UserService(db_session)
    
    # Create first user
    user1 = await service.create_user(UserCreate(email="test@example.com"))
    assert user1.email == "test@example.com"
    
    # Attempt duplicate
    with pytest.raises(ConflictError, match="already exists"):
        await service.create_user(UserCreate(email="test@example.com"))
```

### Integration Tests

```python
async def test_create_duplicate_user_endpoint(client):
    """Test that duplicate user returns 409."""
    data = {"email": "test@example.com", "name": "Test"}
    
    # First request succeeds
    response1 = await client.post("/api/v1/users", json=data)
    assert response1.status_code == 201
    
    # Second request returns 409
    response2 = await client.post("/api/v1/users", json=data)
    assert response2.status_code == 409
    assert response2.json()["error_type"] == "conflict"
    assert "already exists" in response2.json()["detail"]
```

## Checklist for New Endpoints

When creating a new endpoint:

- [ ] CRUD layer catches `IntegrityError` and raises `ConflictError`
- [ ] CRUD layer rolls back transaction on error
- [ ] Service layer documents exceptions in docstring
- [ ] Service layer validates business rules
- [ ] Endpoint layer catches expected exceptions
- [ ] Endpoint layer uses helper functions for HTTP exceptions
- [ ] Error messages are user-friendly (no database internals)
- [ ] Unit tests cover error cases
- [ ] Integration tests verify HTTP status codes

## Anti-Patterns to Avoid

❌ **Don't catch generic Exception in endpoints**
```python
# BAD
try:
    return await service.create_user(data)
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
```

❌ **Don't expose database error messages**
```python
# BAD
except IntegrityError as e:
    raise HTTPException(status_code=400, detail=str(e))
```

❌ **Don't forget to rollback on error**
```python
# BAD
try:
    await db.commit()
except IntegrityError:
    raise ConflictError("Duplicate")  # Missing rollback!
```

❌ **Don't use generic status codes**
```python
# BAD
raise HTTPException(status_code=400, detail="Already exists")  # Should be 409
```

❌ **Don't catch exceptions you can't handle**
```python
# BAD
try:
    return await service.create_user(data)
except Exception:
    pass  # Silently swallowing errors!
```

## References

- [FastAPI Exception Handling](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- [HTTP Status Codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status)
- [SQLAlchemy Exceptions](https://docs.sqlalchemy.org/en/20/core/exceptions.html)
- [REST API Error Handling Best Practices](https://www.rfc-editor.org/rfc/rfc7807)
