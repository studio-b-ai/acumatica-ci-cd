# GCS SDK DLLs + Pipeline Auto-Build Design

**Date:** 2026-04-06
**Goal:** Eliminate manual DLL commits by storing Acumatica SDK DLLs in GCS and building the extension library automatically in CI.

## Problem

The pipeline can't build StudioB.Containers.dll because:
1. The `check_csproj` step looks in `Customization/` but csproj files are in `src/`
2. Acumatica SDK reference DLLs (~53MB) are gitignored and not available in CI
3. The DLL in `Customization/AesthetikContainers/Bin/` is manually built and committed

## Solution

### 1. GCS Bucket for SDK DLLs

- **Bucket:** `gs://aesthetik-acumatica-sdk/` in `aesthetik-production-488816`
- **Structure:** `gs://aesthetik-acumatica-sdk/{version}/*.dll` (e.g., `24.208/PX.Data.dll`)
- **DLLs stored:** PX.Data.dll (11MB), PX.Objects.dll (38MB), PX.Data.BQL.Fluent.dll (164KB), PX.Common.dll (235KB), PX.Common.Std.dll (503KB), PX.DbServices.dll (595KB), PX.Web.Customization.dll (2.2MB)
- **Total:** ~53MB per version
- **Version source:** `acuops.yaml` already has `acumatica_version` field

### 2. Workload Identity Federation (keyless GCP auth)

- **Workload Identity Pool:** `github-actions` in `aesthetik-production-488816`
- **OIDC Provider:** `token.actions.githubusercontent.com`, restricted to `studio-b-ai/acumatica-ci-cd`
- **Service Account:** `github-ci@aesthetik-production-488816.iam.gserviceaccount.com`
- **Permissions:** `roles/storage.objectViewer` on the SDK bucket only
- **GitHub Secrets:** `GCP_WORKLOAD_IDENTITY_PROVIDER` (pool resource name), `GCP_SERVICE_ACCOUNT` (SA email)

### 3. Pipeline Changes (acuops-deploy.yml)

**New steps before packaging:**

```yaml
- name: Authenticate to GCP
  uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
    service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}

- name: Download Acumatica SDK
  if: steps.check_csproj.outputs.has_csproj == 'true'
  run: |
    SDK_VERSION=$(python3 -c "import yaml; print(yaml.safe_load(open('acuops.yaml'))['acumatica_version'])")
    mkdir -p lib
    gsutil -m cp "gs://aesthetik-acumatica-sdk/${SDK_VERSION}/*.dll" lib/
```

**Updated check_csproj:** Look in `src/` instead of `Customization/`

**Updated build step:** Build from repo root, copy DLL into Customization Bin:
```yaml
- name: Build C# extension library
  if: steps.check_csproj.outputs.has_csproj == 'true'
  run: |
    for proj in src/*/*.csproj; do
      dotnet restore "$proj"
      dotnet build "$proj" --configuration Release --no-restore
    done
    # Copy built DLLs to customization Bin directories
    for dll in src/*/bin/Release/net48/*.dll; do
      name=$(basename "$dll")
      find Customization -type d -name Bin -exec cp "$dll" {} \;
    done
```

### 4. What Changes

| Before | After |
|--------|-------|
| DLL manually built locally and committed | Pipeline builds from source automatically |
| SDK DLLs downloaded per lib/README.md | Pipeline downloads from GCS bucket |
| `check_csproj` looks in `Customization/` | Looks in `src/` |
| Build runs in `Customization/` directory | Builds each csproj in `src/` |

### 5. What Stays the Same

- `lib/README.md` — still documents local dev setup
- `lib/*.dll` in `.gitignore` — SDK DLLs never committed
- `Customization/*/Bin/*.dll` — still packaged into the zip (pipeline builds fresh)
- `acuops.yaml` structure — unchanged

### 6. GCE VM

The test VM (n2-standard-4, `aesthetik-production-488816`) is kept for occasional Visual Studio debugging but should be **stopped when idle** (~$0.19/hr = ~$140/month if left running). The GCS bucket serves the VM too — `gsutil cp` to get SDK DLLs instead of extracting ErpPackage manually.

### 7. Not in Scope

- Removing `Customization/*/Bin/*.dll` from git (keep as fallback until pipeline build is proven)
- Multi-version SDK support (only 24.208 for now)
- ISV certification tooling
