# Acumatica SDK Reference Assemblies

This directory holds the Acumatica 24.R2 (24.208) reference DLLs needed to compile `StudioB.Containers.dll`. The DLLs are .gitignored — follow these steps to set up your local environment.

## Setup (one-time)

1. Download `ErpPackage.zip` from [builds.acumatica.com](https://builds.acumatica.com/?prefix=builds/24.2/24.208.0020/Packages/)
2. Extract `Files.zip` from the ErpPackage
3. Extract these DLLs from `Files.zip` into this directory:

```bash
unzip ErpPackage.zip Files.zip
unzip Files.zip \
  'Bin/PX.Data.dll' \
  'Bin/PX.Data.BQL.Fluent.dll' \
  'Bin/PX.Data.BQL.Dynamic.dll' \
  'Bin/PX.Objects.dll' \
  'Bin/PX.Common.dll' \
  'Bin/PX.Common.Std.dll' \
  'Bin/PX.Web.Customization.dll' \
  'Bin/PX.DbServices.dll'
mv Bin/*.dll lib/
```

## Required DLLs

| DLL | Size | Purpose |
|-----|------|---------|
| PX.Data.dll | 11 MB | Core framework (DAC base, BQL, PXGraph, attributes) |
| PX.Objects.dll | 38 MB | Business objects (POOrder, SOShipment, InventoryItem) |
| PX.Data.BQL.Fluent.dll | 164 KB | Fluent BQL syntax |
| PX.Data.BQL.Dynamic.dll | 40 KB | Dynamic BQL |
| PX.Common.dll | 235 KB | Common utilities |
| PX.Common.Std.dll | 503 KB | Common standard library |
| PX.Web.Customization.dll | 2.2 MB | CustomizationPlugin base class |
| PX.DbServices.dll | 595 KB | PXDatabase utilities |

## Version matching

These DLLs must match the deployed Acumatica version. Heritage Fabrics runs 24.208. When Acumatica upgrades, re-download the matching ErpPackage and replace these files.

## Verify

After setup, you should be able to build:

```bash
dotnet build src/StudioB.Containers/StudioB.Containers.csproj
```
