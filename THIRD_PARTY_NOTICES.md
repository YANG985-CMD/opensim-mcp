# Third-party components and references

This is an independent MCP adapter, not an official OpenSim or OpenAI product.
OpenSim binaries, DLLs, source code, third-party human models and motion-capture
data are not bundled. The user installs OpenSim separately.

- [OpenSim Core](https://github.com/opensim-org/opensim-core): upstream source,
  C++ API and CLI definitions; Apache-2.0, with separate third-party notices.
- [OpenSim GUI](https://github.com/opensim-org/opensim-gui): Apache-2.0.
  The original startup module links to installed GUI/NetBeans APIs. Those
  upstream modules are not included in the plugin JAR.
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk): MIT;
  installed as a dependency. This adapter pins the v1 FastMCP interface.
- [defusedxml](https://github.com/tiran/defusedxml): PSF license;
  installed as a dependency.
- [Matplotlib](https://github.com/matplotlib/matplotlib), NumPy and Pillow:
  separately installed plotting/image dependencies; their licenses/notices stay
  with the installed packages. Their code and fonts are not bundled in the source ZIP.

The optional Gait2354 regression reads the official locally installed example
model/marker/force-plate files. Those input files are not redistributed; the
validation record includes file hashes and numerical metrics only.

Dependency licenses and notices remain in their installed distributions.
The MIT license in this repository covers the adapter and its original synthetic
slider fixtures. It does not relicense OpenSim, SDKs, dependencies, or external
datasets. The inspected arm26 model is not redistributed here; its original
credits/license must be preserved if independently redistributed.

- ezc3d 1.7.2 (https://github.com/pyomeca/ezc3d): MIT; installed dependency. Included C3D fixtures are original synthetic data, not upstream participant trials.


- [VTK 9.7.1](https://github.com/Kitware/VTK) is an installed mesh-parser dependency
  under its [BSD 3-clause license](https://raw.githubusercontent.com/Kitware/VTK/master/Copyright.txt).
  Its source/binaries are not bundled in this source ZIP. The offline WebGL player
  is original adapter code; no Three.js or remote scripts are bundled.
