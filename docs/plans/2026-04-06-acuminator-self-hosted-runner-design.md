# Acuminator + Local Validate-Publish via Self-Hosted Windows Runner

**Date:** 2026-04-06
**Status:** Design approved, partial implementation (csproj + bootstrap script)
**Depends on:** `acumatica-test` GCE VM with Acumatica ERP installed

## Problem

Tonight's PCC missing-columns crash (TransportMode, LandedCostRefNbr, LandedCostStatus) would have been caught by either:
1. **Acuminator** — Acumatica's own Roslyn static analyzer
2. **Acumatica's validate-publish** — the real publish validator, run against a local instance

Neither is in our pipeline because:
- Acuminator only runs on Windows (crashes with `PlatformNotSupportedException: Named maps are not supported` on macOS/Linux — confirmed tonight with versions 3.1.3 and 4.0.1)
- Our Linux GHA runners can't invoke Acumatica's validate-publish without a live Acumatica instance, which costs money per restart

## Solution

`acumatica-test` GCE VM already has everything we need:
- Windows Server 2022
- .NET Framework 4.8
- Full Acumatica ERP install at `C:\Program Files\Acumatica ERP\`
- Used previously (April 5) for PCC validation during development
- Currently running idle (~$140/mo)

Register it as a **GitHub self-hosted Windows runner**. Run Acuminator and local validate-publish there. Everything else stays on Linux runners.

## Architecture

```
build (linux-latest) ──→ build-validate (self-hosted windows)
  │                             │
  │  - Downloads SDK DLLs       │  - Runs Acuminator static analysis
  │  - Compiles C# to DLL       │  - Runs validate-publish against local Acumatica
  │  - Packages customization   │  - Runs smoke tests on local instance
  │                             │
  ▼                             ▼
              ┌──────────────────┘
              ▼
  sandbox-gate (SaaS sandbox)
              │
              ▼
  deploy (production)
```

The Windows job runs in parallel with the Linux build after `build` completes. Both must pass before `sandbox-gate` runs.

## Components

### 1. Acuminator (csproj-level, Windows-only)

Both `src/StudioB.Containers/StudioB.Containers.csproj` and `src/StudioB.WMS/StudioB.WMS.csproj` get:

```xml
<ItemGroup Condition="'$(OS)' == 'Windows_NT'">
  <PackageReference Include="Acuminator.Analyzers" Version="4.0.1">
    <PrivateAssets>all</PrivateAssets>
    <IncludeAssets>runtime; build; native; contentfiles; analyzers</IncludeAssets>
  </PackageReference>
</ItemGroup>
```

Condition ensures it only activates on Windows. Linux builds remain clean.

Verified on macOS: 0 warnings, 0 errors for Containers. 7 pre-existing obsolete API warnings for WMS (same as CI). Conditional works.

### 2. Bootstrap script

`scripts/vm/bootstrap-acumatica-test.ps1` — installs .NET 8 SDK, Git for Windows, and downloads the GitHub Actions runner binary. Does NOT register the runner (requires a token from the GitHub API at runtime).

Post-bootstrap manual steps:
1. On local machine: `gh api --method POST repos/studio-b-ai/acumatica-ci-cd/actions/runners/registration-token --jq .token`
2. On VM: `cd C:\actions-runner && .\config.cmd --url https://github.com/studio-b-ai/acumatica-ci-cd --token <TOKEN> --name acumatica-test --labels self-hosted,windows,acumatica-sdk --unattended --replace`
3. On VM: `.\svc.sh install && .\svc.sh start`

### 3. Workflow job (NOT YET IMPLEMENTED)

Add to `.github/workflows/acuops-deploy.yml`:

```yaml
build-validate:
  name: Build + Static Analysis + Local Publish
  needs: build
  runs-on: [self-hosted, windows, acumatica-sdk]
  timeout-minutes: 30
  steps:
    - uses: actions/checkout@v4
    - name: Download package artifact
      uses: actions/download-artifact@v4
      with:
        name: customization-package
        path: dist/

    - name: Copy SDK DLLs from local Acumatica install
      shell: pwsh
      run: |
        $siteBin = "C:\Program Files\Acumatica ERP\Customization\AcumaticaTest\AcumaticaTestValidation\AcumaticaTestWebsite\Bin"
        New-Item -ItemType Directory -Force -Path lib | Out-Null
        Copy-Item "$siteBin\PX.Data.dll" lib\
        Copy-Item "$siteBin\PX.Objects.dll" lib\
        Copy-Item "$siteBin\PX.Data.BQL.Fluent.dll" lib\
        Copy-Item "$siteBin\PX.Common.dll" lib\
        Copy-Item "$siteBin\PX.Common.Std.dll" lib\
        Copy-Item "$siteBin\PX.DbServices.dll" lib\
        Copy-Item "$siteBin\PX.Web.Customization.dll" lib\

    - name: Build with Acuminator
      shell: pwsh
      run: |
        dotnet build src\StudioB.Containers\StudioB.Containers.csproj -c Release
        dotnet build src\StudioB.WMS\StudioB.WMS.csproj -c Release

    - name: Local validate-publish
      shell: pwsh
      env:
        ACUMATICA_URL: http://localhost/AcumaticaTest
        ACUMATICA_USERNAME: admin
        ACUMATICA_PASSWORD: ${{ secrets.LOCAL_ACUMATICA_PASSWORD }}
        ACUMATICA_TENANT: Company
      run: |
        python scripts/deploy.py --validate-only `
          --project ${{ needs.build.outputs.project_name }} `
          --package dist\${{ needs.build.outputs.package_name }}
```

And update `sandbox-gate`:
```yaml
needs: [build, qualify, build-validate]
```

### 4. Triage workflow

First Acuminator run will probably find existing issues. Process:
1. Run `dotnet build` locally on the VM (once it's set up), capture full output
2. Categorize diagnostics:
   - **Real issues**: fix
   - **Acumatica-suggested but not applicable**: suppress via `.editorconfig`
   - **Noise**: suppress
3. Turn on `-warnaserror` only after the backlog is cleared

## What's in scope tonight

- [x] Add Acuminator PackageReference (Windows-only conditional) to both csprojs
- [x] Write bootstrap script for the VM
- [x] Write this design doc
- [ ] Commit and push
- [ ] PR

## What's NOT in scope tonight

- Running the bootstrap script on the VM (manual step, needs RDP/SSH access)
- Registering the runner with GitHub (needs token)
- Adding the `build-validate` workflow job (needs runner to exist first)
- Running first Acuminator scan (needs workflow wired up)
- Triage of Acuminator findings (depends on first scan)
- Configuring local Acumatica `validate-only` step (needs local credentials set up)

## Next steps after tonight

1. SSH/RDP to `acumatica-test` VM
2. Run `bootstrap-acumatica-test.ps1` as Administrator
3. Generate runner token, register the runner, install as service
4. Verify runner shows up at https://github.com/studio-b-ai/acumatica-ci-cd/settings/actions/runners
5. Add `build-validate` job to workflow (PR)
6. Trigger a test workflow run, see what Acuminator finds
7. Triage, suppress, fix
8. Add local validate-publish step once credentials are configured
9. Turn on `-warnaserror` for Acuminator rules we care about

## Cost note

`acumatica-test` VM costs ~$140/mo if left running 24/7. Leaving it running for now — cost is negligible compared to bad deploys. Can optimize with start/stop later.

## Security note

Self-hosted runners can execute arbitrary code from workflows. Our repo is private, so this is acceptable, but:
- Configure the runner to only accept jobs from this specific repo (not org-wide)
- Don't run PR workflows from forks against this runner
- Rotate the runner token periodically
