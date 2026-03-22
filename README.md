# AI DPA Analyzer 🛡️

![Next.js](https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)

> **Stop Overpaying Lawyers. Startups die by unlimited liability clauses.**

AI DPA Analyzer is an advanced, open-source platform designed to automatically analyze Data Processing Agreements (DPAs) for startups. It identifies critical legal risks, compliance gaps, and provides actionable feedback, empowering founders to sign agreements with confidence.

---

## 🚀 Features

- **Automated Risk Analysis:** Upload a DPA and receive a comprehensive risk report highlighting unlimited liability clauses, compliance issues, and unfair terms.
- **DPA Registry & Versioning:** Tracks, fetches, and computes diffs for standard DPAs from major SaaS service providers.
- **Vector Search & Embeddings:** Leverages PostgreSQL with `pgvector` for semantic search and intelligent retrieval of legal clauses.
- **Premium Scrollytelling UI:** A sleek, brutalist Next.js frontend powered by GSAP and Framer Motion for a world-class user experience.
- **Scalable Architecture:** Built as a modern monorepo using Turborepo, cleanly separating frontend, backend services, and Python evaluation packages.

## 🛠 Tech Stack

- **Frontend:** Next.js (App Router), Tailwind CSS, GSAP, Framer Motion, TypeScript.
- **Backend Services:** Python, SQLAlchemy, Alembic, Pydantic, PostgreSQL + `pgvector`.
- **Monorepo Management:** pnpm, Turborepo.

## 📂 Repository Structure

This repository is organized as a Turborepo monorepo to maximize code sharing and build efficiency:

```text
ai-dpa/
├── apps/
│   ├── api/        # Python backend API & database models
│   ├── web/        # Next.js frontend web application
│   └── worker/     # Python worker for async tasks (parsing, evaluation)
├── packages/
│   ├── checklist/  # Core DPA risk checklist definitions and logic
│   ├── eval/       # Evaluation schemas and frameworks for AI outputs
│   ├── registry/   # CLI & services for fetching, normalizing, and diffing standard DPAs
│   └── schemas/    # Shared JSON and Pydantic schemas across the monorepo
└── ...
```

## 💻 Getting Started

### Prerequisites

- [Node.js](https://nodejs.org/) (v18+) & [pnpm](https://pnpm.io/)
- [Python 3.10+](https://www.python.org/)
- PostgreSQL with the [`pgvector`](https://github.com/pgvector/pgvector) extension (using Docker is highly recommended).

### 1. Clone the repository

```bash
git clone https://github.com/your-username/ai-dpa.git
cd ai-dpa
```

### 2. Setup Node Environment (Frontend & Monorepo Tools)

```bash
# Install all node dependencies
pnpm install

# Build all packages and apps
pnpm run build
```

### 3. Setup Python Environment (Backend)

We strongly recommend using a virtual environment.

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate

# Install requirements for API and workers
pip install -r apps/api/requirements.txt

# start backend

cd apps/api & uvicorn upload_api.main:app --reload --host 127.0.0.1 --port 8001
```

### 4. Database Configuration

Ensure your Postgres+pgvector database is running. Create a `.env` file at the root or within `apps/api` with your connection string. 

To initialize the database schema, run the Alembic migrations using the provided Makefile:

```bash
make db-upgrade
```

### 5. Managing the DPA Registry

The project includes a Python CLI to manage a registry of DPAs:

```bash
make registry-seed     # Seed the initial registry
make registry-fetch    # Fetch new DPAs
make registry-diff     # Compute diffs between versions
make registry-status   # View current registry status
```

## 🧪 Testing

The repository uses unified testing commands for both ecosystems.

**Run Node/TypeScript tests:**
```bash
pnpm run test
```

**Run Python backend tests:**
```bash
make test
```

## 🤝 Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
