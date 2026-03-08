# SomaAI Environment Manifest

This document provides a comprehensive overview of all environment variables used by the SomaAI system, their roles, security levels, and implementation rationale from a Principal DevOps perspective.

## 🏗️ Architecture Design Principle

The system implements the **"Twelve-Factor App" III. Config** principle: *Store config in the environment as environment variables.*

| Feature | Design Rationale |
| :--- | :--- |
| **Env Prefix (`SOMAAI_`)** | Decouples the app from the host OS. Prevents collision with generic variables like `DEBUG` or `PORT` in shared cluster environments. |
| **Validation Alias** | Supports legacy environments via `AliasChoices`, allowing a seamless migration to the prefixed standard. |
| **Secret Masking** | Uses `pydantic.SecretStr` for all sensitive fields. This prevents accidental exposure in CI/CD logs, logging systems (e.g., Splunk/ELK), and error traces. |
| **Strong Typing** | Startup will **fail immediately** if a variable is malformed (e.g., `PORT="string"`), ensuring fail-fast reliability. |

---

## 🛰️ Infrastructure & Roles

### 1. Application Core
| Variable | Default | Role |
| :--- | :--- | :--- |
| `SOMAAI_DEBUG` | `false` | Enables hot-reload, detailed traceback, and `MockLLM` fallback logic for development. |
| `SOMAAI_APP_NAME` | `"SomaAI"` | Application identifier for telemetry and logs. |
| `SOMAAI_PORT` | `8000` | Target port for API traffic. |

### 2. Primary Persistent Storage (PostgreSQL)
The relational database handles users, curriculum metadata, and job states.
| Variable | Default | Role |
| :--- | :--- | :--- |
| `SOMAAI_DATABASE_URL` | `sqlite...` | Full DSN for Async PostgreSQL (`postgresql+asyncpg://...`). |
| `SOMAAI_DB_POOL_SIZE` | `10` | Permanent connection pool size. Increase for high-concurrency workloads. |
| `SOMAAI_DB_MAX_OVERFLOW`| `20` | Dynamic buffer for connection spikes. |

### 3. Distributed Cache & Async Operations (Redis)
Redis serves three distinct mission-critical functions.
| Variable | Default | Role |
| :--- | :--- | :--- |
| `SOMAAI_REDIS_URL` | `.../0` | DB 0: General API and session cache. |
| `SOMAAI_REDIS_JOBS_URL`| `.../1` | DB 1: Shared Task Queue state for ARQ workers. |
| `SOMAAI_REDIS_CACHE_URL`| `.../2` | DB 2: Semantic RAG retrieval cache (deduplication store). |
| `SOMAAI_REDIS_PASSWORD`| `None` | **[SECRET]** Pydantic-masked authentication key. |

### 4. Vector Intelligence (Qdrant)
The "Brain" for our RAG (Retrieval Augmented Generation) pipeline.
| Variable | Default | Role |
| :--- | :--- | :--- |
| `SOMAAI_QDRANT_URL` | `...:6333` | REST/gRPC endpoint for similarity search operations. |
| `SOMAAI_QDRANT_API_KEY`| `None` | **[SECRET]** Secure authentication for managed Qdrant instances. |

### 5. Object Storage (MinIO / S3)
| Variable | Default | Role |
| :--- | :--- | :--- |
| `SOMAAI_STORAGE_BACKEND`| `minio` | Toggles between local S3-compatible (MinIO) or native AWS S3. |
| `SOMAAI_MINIO_ENDPOINT`| `...:9000` | Local development storage endpoint. |
| `SOMAAI_S3_SECRET_KEY` | `None` | **[SECRET]** AWS Secret Key for production file storage. |

### 6. AI & LLM Connectivity
| Variable | Default | Role |
| :--- | :--- | :--- |
| `SOMAAI_LLM_BACKEND` | `groq` | Strategy selector for LLM intelligence (`groq` / `openai` / `mock`). |
| `SOMAAI_GROQ_API_KEY` | `None` | **[SECRET]** Token for Groq's high-performance inference. |
| `SOMAAI_OPENAI_API_KEY`| `None` | **[SECRET]** Token for OpenAI backend fallback. |

---

## 🛡️ DevOps Checklist for Deployment
1.  **Prefix Enforcement**: Ensure all environment variables in your Docker/K8s manifest use the `SOMAAI_` prefix.
2.  **Strict Security**: Set `SOMAAI_REQUIRE_API_KEY=true` in any production or internet-facing environment.
3.  **Performance**: Tune `SOMAAI_DB_POOL_SIZE` based on the number of worker replicas (Total Pool = Replicas × Pool Size).
