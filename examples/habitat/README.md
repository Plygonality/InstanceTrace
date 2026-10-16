# HK Habitat Module

Offline facade used by `instancetrace demo`. Two nested groups (`BayModule`, and inside it `WindowScatter` plus `MullionScatter`) instance three source families: `Panel_A`, `Panel_B`, and `Mullion`. Sample keys are authored integers. Windows whose sample key is divisible by 11 are filtered out. Mullions hang off the surviving windows.

Regenerate with:

```bash
instancetrace demo --out examples/habitat
```

`lineage.dot` and `lineage.html` highlight one live bay-L panel. `continuity.json` compares seed 218 with a right-bay seed of 219. `loss/lineage.txt` is the same logical id after a realize step that drops an exact parent.

Meshes in the Blender fixture are generated quads. This directory does not contain a mesh file.
