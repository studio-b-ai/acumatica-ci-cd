# GCS SDK DLLs + Pipeline Auto-Build Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Store Acumatica SDK DLLs in GCS and auto-build extension libraries in CI, eliminating manual DLL commits.

**Architecture:** Create a GCS bucket with versioned SDK DLLs, set up Workload Identity Federation for keyless GitHub Actions auth, update the pipeline to download SDKs and build csproj files from `src/`, and copy built DLLs into the customization package.

**Tech Stack:** gcloud CLI, GCS, Workload Identity Federation, GitHub Actions, dotnet CLI

---

## Task 1: Create GCS Bucket and Upload SDK DLLs

**Goal:** One-time infrastructure setup — bucket + initial DLL upload.

### Step 1: Create the bucket

```bash
/opt/homebrew/bin/gcloud storage buckets create gs://aesthetik-acumatica-sdk \
  --project=aesthetik-production-488816 \
  --location=us-central1 \
  --uniform-bucket-level-access
```

### Step 2: Upload SDK DLLs

The SDK DLLs are currently in `lib/` (extracted from ErpPackage.zip earlier in this session).

```bash
/opt/homebrew/bin/gcloud storage cp lib/PX.*.dll gs://aesthetik-acumatica-sdk/24.208/
```

### Step 3: Verify upload

```bash
/opt/homebrew/bin/gcloud storage ls gs://aesthetik-acumatica-sdk/24.208/
```

Expected: 7 DLL files listed.

---

## Task 2: Set Up Workload Identity Federation

**Goal:** Allow GitHub Actions to authenticate to GCP without stored keys.

### Step 1: Create the Workload Identity Pool

```bash
/opt/homebrew/bin/gcloud iam workload-identity-pools create github-actions \
  --project=aesthetik-production-488816 \
  --location=global \
  --display-name="GitHub Actions"
```

### Step 2: Create the OIDC Provider

```bash
/opt/homebrew/bin/gcloud iam workload-identity-pools providers create-oidc github \
  --project=aesthetik-production-488816 \
  --location=global \
  --workload-identity-pool=github-actions \
  --display-name="GitHub" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository_owner=='studio-b-ai'"
```

### Step 3: Create the Service Account

```bash
/opt/homebrew/bin/gcloud iam service-accounts create github-ci \
  --project=aesthetik-production-488816 \
  --display-name="GitHub CI"
```

### Step 4: Grant Storage Object Viewer on the bucket

```bash
/opt/homebrew/bin/gcloud storage buckets add-iam-policy-binding gs://aesthetik-acumatica-sdk \
  --member="serviceAccount:github-ci@aesthetik-production-488816.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

### Step 5: Allow GitHub Actions to impersonate the service account

```bash
/opt/homebrew/bin/gcloud iam service-accounts add-iam-policy-binding \
  github-ci@aesthetik-production-488816.iam.gserviceaccount.com \
  --project=aesthetik-production-488816 \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe aesthetik-production-488816 --format='value(projectNumber)')/locations/global/workloadIdentityPools/github-actions/attribute.repository/studio-b-ai/acumatica-ci-cd"
```

### Step 6: Get the WIF provider resource name

```bash
/opt/homebrew/bin/gcloud iam workload-identity-pools providers describe github \
  --project=aesthetik-production-488816 \
  --location=global \
  --workload-identity-pool=github-actions \
  --format="value(name)"
```

Save the output — it looks like: `projects/NNNNN/locations/global/workloadIdentityPools/github-actions/providers/github`

### Step 7: Store GitHub secrets

```bash
/opt/homebrew/bin/gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER \
  --repo studio-b-ai/acumatica-ci-cd \
  --body "<value from step 6>"

/opt/homebrew/bin/gh secret set GCP_SERVICE_ACCOUNT \
  --repo studio-b-ai/acumatica-ci-cd \
  --body "github-ci@aesthetik-production-488816.iam.gserviceaccount.com"
```

---

## Task 3: Update Pipeline — Download SDK and Build DLL

**Files:**
- Modify: `.github/workflows/acuops-deploy.yml`

### Step 1: Add GCP auth step

After the "Setup Python" step (around line 340), add:

```yaml
      - name: Authenticate to GCP
        id: gcp_auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}
```

### Step 2: Update check_csproj to look in src/

Replace lines 348-357:

```yaml
      - name: Check for C# extension library
        id: check_csproj
        run: |
          if ls src/*/*.csproj 1>/dev/null 2>&1; then
            echo "has_csproj=true" >> "$GITHUB_OUTPUT"
            echo "Found C# project(s) in src/ — will build extension library"
          else
            echo "has_csproj=false" >> "$GITHUB_OUTPUT"
            echo "No C# project — packaging XML/ASPX only"
          fi
```

### Step 3: Add SDK download step

Replace the "Setup .NET" step and add SDK download:

```yaml
      - name: Setup .NET (if C# extension exists)
        if: steps.check_csproj.outputs.has_csproj == 'true'
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '6.0.x'

      - name: Download Acumatica SDK from GCS
        if: steps.check_csproj.outputs.has_csproj == 'true'
        run: |
          SDK_VERSION=$(python3 -c "import yaml; c=yaml.safe_load(open('acuops.yaml')); print(c.get('acumatica_build_version', '24.208'))")
          echo "Downloading Acumatica SDK ${SDK_VERSION}..."
          mkdir -p lib
          gsutil -m cp "gs://aesthetik-acumatica-sdk/${SDK_VERSION}/*.dll" lib/
          echo "SDK DLLs downloaded:"
          ls -lh lib/*.dll
```

### Step 4: Update the build step

Replace lines 365-371:

```yaml
      - name: Build C# extension library
        if: steps.check_csproj.outputs.has_csproj == 'true'
        run: |
          for proj in src/*/*.csproj; do
            echo "Building $(basename $proj)..."
            dotnet restore "$proj"
            dotnet build "$proj" --configuration Release --no-restore
          done

          # Copy built DLLs into customization Bin directories
          for dll in src/*/bin/Release/net48/*.dll; do
            DLLNAME=$(basename "$dll")
            for bindir in Customization/*/Bin; do
              if [ -d "$bindir" ]; then
                cp "$dll" "$bindir/"
                echo "Copied $DLLNAME → $bindir/"
              fi
            done
          done
```

### Step 5: Add acumatica_build_version to acuops.yaml

Add to `acuops.yaml`:

```yaml
acumatica_build_version: "24.208"
```

### Step 6: Add permissions for WIF token

At the top of the `build` job, add the `permissions` block needed for Workload Identity Federation:

```yaml
    permissions:
      contents: read
      id-token: write
```

The `id-token: write` permission is required for the GitHub OIDC token that WIF exchanges for GCP credentials.

### Step 7: Commit

```bash
git add .github/workflows/acuops-deploy.yml acuops.yaml
git commit -m "feat: auto-build extension DLLs from GCS SDK in pipeline

- GCS bucket gs://aesthetik-acumatica-sdk stores Acumatica SDK DLLs
- Workload Identity Federation for keyless GCP auth
- Pipeline downloads SDK, builds csproj files from src/
- Built DLLs copied to Customization/*/Bin/ for packaging
- Added acumatica_build_version to acuops.yaml"
```

---

## Task 4: Test the Pipeline

### Step 1: Push and trigger

```bash
git push origin claude/jovial-montalcini
```

Then trigger manually:
```bash
gh workflow run "AcuOps Deploy" --repo studio-b-ai/acumatica-ci-cd \
  --ref claude/jovial-montalcini -f environment=staging
```

### Step 2: Verify

Check the pipeline run:
- "Authenticate to GCP" step succeeds
- "Download Acumatica SDK from GCS" downloads 7 DLLs
- "Build C# extension library" builds StudioB.Containers.dll (and StudioB.WMS.dll)
- "Package customization project" includes the freshly built DLL
- Deploy to staging succeeds

### Step 3: Verify on sandbox

- SB501000 loads with TransportMode dropdown
- PO Links grid shows vendor name and stock item columns

---

## Task 5: Clean Up — Remove Committed DLL from Git (optional, after proven)

Once the pipeline auto-build is proven working across 2-3 deploys:

```bash
echo "Customization/*/Bin/*.dll" >> .gitignore
git rm --cached Customization/AesthetikContainers/Bin/StudioB.Containers.dll
git commit -m "chore: stop tracking compiled DLLs — pipeline builds them now"
```

This is optional and should wait until the auto-build is proven reliable.
