# Spiral Milling Algorithm Explained

## Visual Representation

### Straight Drill (Hole ≤ Bit Size)
```
     Top View              Side View
        
     ┌───┐                   │
     │ ● │                   │ ↓ Plunge
     └───┘                   │
    Bit Size                 │___
                             
    Simple plunge down and up
```

### Spiral Mill (Hole > Bit Size)

```
     Top View - Spiral Path
     
     ┌─────────────┐
     │             │
     │    ┌───┐   │  ← Hole outline
     │   ╱  ●  ╲  │
     │  │   │   │ │
     │   ╲  │  ╱  │  ← Bit path (spiral)
     │    └─┼─┘   │
     │      ↓     │
     └─────────────┘
     
     Center → Radius → Spiral down
```

## Algorithm Details

### Step 1: Calculate Milling Radius
```
Given:
  - Hole diameter: 3.0 mm
  - Bit diameter: 1.0 mm
  
Calculate:
  - Hole radius = 3.0 / 2 = 1.5 mm
  - Bit radius = 1.0 / 2 = 0.5 mm
  - Milling radius = 1.5 - 0.5 = 1.0 mm
  
The bit center travels at 1.0mm from hole center,
so the outer edge of the bit cuts exactly at 1.5mm radius.
```

### Step 2: Divide Depth into Passes
```
Given:
  - Total depth: 2.0 mm
  - Step per pass: 0.5 mm
  
Calculate:
  - Number of passes = ceil(2.0 / 0.5) = 4 passes
  - Actual step = 2.0 / 4 = 0.5 mm per pass
  
Passes: 0.0 → -0.5 → -1.0 → -1.5 → -2.0 mm
```

### Step 3: Generate Circular Path
```
For each pass:
  - Divide circle into 36 segments (10° each)
  - Calculate X,Y for each segment:
    
    X = center_x + radius × cos(angle)
    Y = center_y + radius × sin(angle)
    
  - First segment: move X, Y, and Z (spiral down)
  - Remaining segments: move X, Y only (circular)
```

## Example Coordinates

### 3mm Hole at (50, 50) with 1mm Bit

**Milling radius = 1.0 mm**

```
Pass 1 (Z = -0.5):
  Segment 0   (0°):   X=51.000, Y=50.000, Z=-0.500  (spiral)
  Segment 1  (10°):   X=50.985, Y=50.174, Z=-0.500  (circle)
  Segment 2  (20°):   X=50.940, Y=50.342, Z=-0.500
  ...
  Segment 36 (360°):  X=51.000, Y=50.000, Z=-0.500  (close)

Pass 2 (Z = -1.0):
  Segment 0   (0°):   X=51.000, Y=50.000, Z=-1.000  (spiral)
  ...

Pass 3 (Z = -1.5):
  ...

Pass 4 (Z = -2.0):
  ...
```

## Feed Rates

```
Movement Type          Feed Rate    Purpose
─────────────────────────────────────────────
Rapid positioning     Max (G0)     Safe moves
First segment (Z)     50 mm/min    Controlled plunge
Circle segments (XY)  100 mm/min   Smooth cutting
Return to center      100 mm/min   Exit cut
Retract              Max (G0)     Fast exit
```

## Why This Works

### 1. Bit Radius Compensation
```
Cutting circle radius = Hole radius - Bit radius

Example:
  6mm hole, 1mm bit:
  Mill at radius 3.0 - 0.5 = 2.5 mm
  
  Bit center at 2.5mm → Outer edge at 3.0mm ✓
```

### 2. Gradual Z Descent
```
Instead of:               Use:
  Plunge → Circle         Spiral down while circling
  
Reduces:
  - Tool load
  - Chatter
  - Bit breakage
  
Increases:
  - Smooth cutting
  - Better surface finish
```

### 3. Closed Circles
```
Each pass makes complete circle:
  Start angle: 0°
  End angle: 360° (same as 0°)
  
Ensures:
  - Clean, complete cuts
  - No gaps
  - Uniform hole
```

## Optimization Techniques

### 1. Segment Count
```
More segments = smoother circle = larger G-code file
Current: 36 segments (10° each)

Options:
  - 18 segments: Faster but less smooth
  - 72 segments: Smoother but larger file
```

### 2. Z Step Size
```
Smaller steps = smoother descent = more passes
Current: 0.5 mm steps

Options:
  - 0.25 mm: Smoother, slower
  - 1.0 mm: Faster, more aggressive
```

### 3. Entry Strategy
```
Current: Entry at radius edge
Alternative: Entry at center, spiral outward

Trade-offs:
  Edge entry: Cleaner center
  Center entry: Less stress on first plunge
```

## Common Issues & Solutions

### Issue: Hole too small
```
If milling_radius ≤ 0:
  → Fall back to straight drill
  
Example:
  1.0mm hole, 1.2mm bit
  Radius = 0.5 - 0.6 = -0.1 (invalid)
  Solution: Use straight drill
```

### Issue: Deep holes
```
If depth > 5mm:
  → Consider peck drilling
  → Or reduce Z step to 0.25mm
```

### Issue: Hard materials
```
If material is hard:
  → Reduce feed rate (50-80 mm/min)
  → Reduce Z step (0.25mm)
  → Increase spindle speed
```

## G-code Example

```gcode
(Spiral mill 3mm hole at X50 Y50)
G0 X50.0000 Y50.0000      ; Move to center
G0 Z2.000                 ; Clearance height
G1 X51.0000 Y50.0000 F100.0  ; Move to start radius

; Pass 1: Z=-0.5
G1 X51.0000 Y50.0000 Z-0.5 F50.0  ; Spiral down
G1 X50.9848 Y50.1736 F100.0       ; Circle segment 1
G1 X50.9397 Y50.3420 F100.0       ; Circle segment 2
; ... 34 more segments ...
G1 X51.0000 Y50.0000 F100.0       ; Close circle

; Pass 2: Z=-1.0
G1 X51.0000 Y50.0000 Z-1.0 F50.0  ; Spiral down
; ... circle segments ...

; Pass 3: Z=-1.5
; ...

; Pass 4: Z=-2.0 (final depth)
; ...

G1 X50.0000 Y50.0000 F100.0  ; Return to center
G0 Z2.000                    ; Retract
```

## Arc Moves (G2/G3)

```
Arc moves use helical interpolation to create a true circular spiral in a single command per pass.
Example helical arc (clockwise) format used by this tool:

G2 X{end_x:.4f} Y{end_y:.4f} Z{end_z:.4f} I{offset_i:.4f} J{offset_j:.4f} F{feed}

Where:
- `X Y` are the end coordinates (for a full circle these equal the start XY)
- `Z` is the end Z depth for that pass (creates the helix)
- `I J` are offsets from the current position to the arc center
- `F` is the feed/plunge rate

Advantages:
- Much smaller G-code (one arc per pass instead of many segments)
- True circular motion (no faceting)
- Controller does the heavy lifting for arc interpolation

Example (3mm hole, 1mm bit, 4 passes):

G0 X50.0000 Y50.0000 (Move to center)
G0 Z2.000 (Clearance)
G1 X51.0000 Y50.0000 F100.0 (Start radius)
G2 X51.0000 Y50.0000 Z-0.5000 I-1.0000 J0.0000 F50.0
G2 X51.0000 Y50.0000 Z-1.0000 I-1.0000 J0.0000 F50.0
G2 X51.0000 Y50.0000 Z-1.5000 I-1.0000 J0.0000 F50.0
G2 X51.0000 Y50.0000 Z-2.0000 I-1.0000 J0.0000 F50.0
G1 X50.0000 Y50.0000 F100.0 (Return to center)
G0 Z2.000 (Retract)
```

Note: Use the `--use-arcs` flag to enable arc-mode output when your controller supports G2/G3.

## Mathematical Formulas

### Circular Path
```python
for i in range(segments + 1):
    angle = i * (2 * π / segments)
    x = center_x + radius * cos(angle)
    y = center_y + radius * sin(angle)
```

### Spiral Depth
```python
num_passes = ceil(total_depth / z_step)
for pass_num in range(num_passes):
    z = -(pass_num + 1) * z_step
```

### Milling Radius
```python
mill_radius = (hole_diameter - bit_diameter) / 2
if mill_radius <= 0:
    use_straight_drill()
else:
    use_spiral_mill()
```

---

**This algorithm ensures precise, smooth holes every time!** 🎯
