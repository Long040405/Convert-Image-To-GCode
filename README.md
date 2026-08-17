# Industrial Vision & Image to G-Code Pipeline

An end-to-end computer vision and G-Code generation system designed for 3-Axis CNC machines, Plotters, and Linear Motion Systems (X, Y, Z), featuring industrial Basler GigE camera acquisition, illumination leveling, vectorization, and toolpath simulation.


**SYSTEM WORKFLOW & PIPELINE**

The complete processing workflow consists of 4 sequential modules:

1. Vision Acquisition (`camera.py`): Real-time GigE camera capture, flat-field calibration, LAB shadow removal, and object isolation.
2. 3D-to-2D Preprocessing (`convert_3d_to_2d.py`): Transforms continuous-tone photographs into clean 2D flat vector art (Line Art, Cartoon, Posterize, Edge, Stipple).
3. G-Code Engine (`image_to_gcode.py`): Converts 2D drawings into optimized CNC G-Code with G2/G3 arc fitting and TSP path ordering.
4. Toolpath Simulator (`gcode_viewer.py`): Step-by-step 2D visual verification and safety inspection before machining.


**DIRECTORY STRUCTURE**

* `camera.py` : Basler GigE camera controller, flat-field calibrator, shadow remover, and capture utility.
* `convert_3d_to_2d.py` : GUI & CLI utility for flattening real-world images into clean vector drawings.
* `image_to_gcode.py` : Advanced G-Code generation engine supporting 7 drawing algorithms and geometric optimization.
* `gcode_viewer.py` : Interactive G-Code visual simulator and verification canvas.
* `flatfield.png` : Reference light field calibration image.
* `captures/` : Default output directory for camera snapshots and extracted objects.
* `requirements.txt` : Python dependencies list.
* `.gitignore` : Git ignore definitions for temporary cache and output files.


**PREREQUISITES & INSTALLATION**

* Recommended Runtime: Python 3.10 or 3.11 (64-bit).
* Hardware: Basler GigE / USB industrial camera (optional for live acquisition) and 3-axis CNC/Plotter.
* Software Dependencies: Install required packages using pip:
  `pip install -r requirements.txt`
* Basler SDK Note: If using physical Basler cameras, install the Basler Pylon Camera Software Suite on Windows.


**MODULE EXECUTION GUIDE**

* **Module 1: Camera Vision Acquisition (`camera.py`)**
  Launch the live video stream with real-time exposure, gain, and illumination correction:
  Command: `python camera.py`
  Keyboard Shortcuts:
  * [Space] or [S] : Capture image, sharpen, isolate object onto white background, and save to `captures/`.
  * [F] : Calibrate flat-field background (run once when field of view contains an empty white surface).
  * [C] : Cycle through Bayer color demosaicing patterns.
  * [Esc] or [Q] : Disconnect camera safely and exit.

* **Module 2: 3D to 2D Preprocessing (`convert_3d_to_2d.py`)**
  Raw photos contain gradients and shadows that cause fragmented toolpaths. Use this module to flatten images:
  GUI Mode: `python convert_3d_to_2d.py`
  CLI Mode: `python convert_3d_to_2d.py input.jpg lineart`
  CLI Batch Mode: `python convert_3d_to_2d.py input.jpg all`
  Supported Methods:
  1. Line Art: Single black contours on white background (optimal for LINE / CONTOUR modes).
  2. Cartoon: Clustered flat color regions with crisp boundary outlines.
  3. Threshold: Adaptive local binarization with automated noise cleanup.
  4. Posterize: Quantizes luminance into 4–8 discrete levels, stripping smooth gradients.
  5. Edge Drawing: Canny edge detector with morphological gap bridging.
  6. Stipple: Variable-density dot patterning for tonal shading.

* **Module 3: Image to G-Code Generation (`image_to_gcode.py`)**
  Converts 2D artwork into standard CNC/Plotter G-Code:
  GUI Mode: `python image_to_gcode.py`
  CLI Mode: `python image_to_gcode.py input.png -o output.gcode --method line`
  7 Drawing Algorithms:
  * LINE : Centerline skeletonization (1px thickness) for uniform stroke drawing.
  * CONTOUR : Perimeter tracing with closed-loop optimization.
  * COLOR : Multi-layer boundary extraction for multi-color pen plotting.
  * PORTRAIT : Normalized Difference of Gaussians (DoG) filter for facial features.
  * RASTER : Area infill patterns (continuous Zigzag, cross-hatching, or offset contours).
  * EDGE : High-precision Canny edge contouring.
  * TEXT : Direct Vietnamese Unicode text engraving without requiring input images.

* **Module 4: G-Code Simulation & Verification (`gcode_viewer.py`)**
  Inspect toolpaths and pen-up/pen-down motions before machining:
  Command: `python gcode_viewer.py output.gcode`
  Controls:
  * Mouse : Scroll to Zoom at cursor, Drag to Pan, Double-click to Fit to View.
  * [Space] : Play / Pause step-by-step toolpath simulation.
  * [R] : Reset simulation to beginning.
  * [F] : Fit view to canvas boundaries.


**KEY TECHNICAL HIGHLIGHTS**

* Intelligent Shadow Elimination: Analyzes LAB color-space chrominance to separate soft cast shadows from physical objects.
* Geometric Arc Fitting: Automatically fits curved point sequences into circular G2/G3 (I/J) arc commands, reducing file size by up to 80% and preventing motor stuttering.
* TSP Toolpath Optimization: Employs nearest-neighbor Traveling Salesperson Problem heuristics to minimize non-cutting rapid travels (G0) and Z-axis hops.
* Full Unicode Support: Robust file path handling for accented characters on Windows.


**LICENSE & USAGE**

Distributed for research, academic, and industrial automation development with CNC and linear motion systems.
