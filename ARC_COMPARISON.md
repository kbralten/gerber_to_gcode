# Arc Moves vs Linear Segments - Comparison Guide

## Overview

The spiral milling feature can generate toolpaths in two different ways:

1. **Linear Segments** (default): Approximates circles with many small straight lines
2. **Arc Moves** (`--use-arcs`): Uses true circular arc commands

## Visual Comparison

### Linear Segments Mode (Default)
```
For a 3mm hole with 1mm bit:
  - 4 passes (Z steps of 0.5mm each)
  - 36 segments per circle
  - Total: 148 G1 commands per hole
```

### Arc Moves Mode (--use-arcs)
```
For a 3mm hole with 1mm bit:
  - 4 passes (Z steps of 0.5mm each)
  - 1 arc per pass
  - Total: 4 G2 commands per hole
```

## File Size Comparison

Test file: `example.drl` (11 holes, 5 require spiral milling)

| Mode | File Size | Reduction | Lines of G-code |
|------|-----------|-----------|-----------------|
| Linear segments | 24,090 bytes | - | ~825 lines |
| Arc moves | 3,668 bytes | **85%** | ~105 lines |

**Result: Arc moves produce files that are ~6.5x smaller!**

## G-code Example: 3mm Hole

### Linear Segments Output
```gcode
(Spiral mill hole: dia 3.0000 mm at X10.0000 Y50.0000)
G0 X10.0000 Y50.0000 (Move to hole center)
G0 Z2.000 (Move to clearance height)
G1 X11.0000 Y50.0000 F100.0 (Move to starting radius)

; First pass at Z=-0.5
G1 X11.0000 Y50.0000 Z-0.5000 F50.0
G1 X10.9848 Y50.1736 F100.0
G1 X10.9397 Y50.3420 F100.0
G1 X10.8660 Y50.5000 F100.0
G1 X10.7660 Y50.6428 F100.0
G1 X10.6428 Y50.7660 F100.0
G1 X10.5000 Y50.8660 F100.0
G1 X10.3420 Y50.9397 F100.0
G1 X10.1736 Y50.9848 F100.0
G1 X10.0000 Y51.0000 F100.0
G1 X9.8264 Y50.9848 F100.0
; ... 26 more segments ...
G1 X11.0000 Y50.0000 F100.0

; Second pass at Z=-1.0
G1 X11.0000 Y50.0000 Z-1.0000 F50.0
; ... 37 more segments ...

; Third pass at Z=-1.5
; ... 37 more segments ...

; Fourth pass at Z=-2.0
; ... 37 more segments ...

G1 X10.0000 Y50.0000 F100.0 (Return to center)
G0 Z2.000 (Retract)
```
**Total: ~150 lines for this one hole**

### Arc Moves Output
```gcode
(Spiral mill hole with arcs: dia 3.0000 mm at X10.0000 Y50.0000)
G0 X10.0000 Y50.0000 (Move to hole center)
G0 Z2.000 (Move to clearance height)
G1 X11.0000 Y50.0000 F100.0 (Move to starting radius)
G2 X11.0000 Y50.0000 Z-0.5000 I-1.0000 J0.0000 F50.0
G2 X11.0000 Y50.0000 Z-1.0000 I-1.0000 J0.0000 F50.0
G2 X11.0000 Y50.0000 Z-1.5000 I-1.0000 J0.0000 F50.0
G2 X11.0000 Y50.0000 Z-2.0000 I-1.0000 J0.0000 F50.0
G1 X10.0000 Y50.0000 F100.0 (Return to center)
G0 Z2.000 (Retract)
```
**Total: 9 lines for this one hole** ✨

## Understanding G2/G3 Arc Commands

### G2 Command Breakdown
```gcode
G2 X11.0000 Y50.0000 Z-0.5000 I-1.0000 J0.0000 F50.0
│  │               │          │                │
│  └── End point   └── End Z  └── Center      └── Feed rate
│                              offset I,J
└── Clockwise arc
```

**How it works:**
- `G2`: Clockwise arc (G3 would be counterclockwise)
- `X Y`: End coordinates (same as start = full circle)
- `Z`: End Z height (creates helical/spiral motion)
- `I J`: Offset from current position to arc center
  - I = X offset = -1.0mm (center is 1mm left of start)
  - J = Y offset = 0.0mm (center is at same Y)
- `F`: Feed rate for the move

### Why This Works

The arc command creates a **helical interpolation**:
- Moves in a perfect circle in the XY plane
- Simultaneously descends in Z
- Result: smooth spiral motion in a single command!

## Performance Comparison

### Loading Time
| File Size | USB Transfer | Parse Time | CNC Buffer |
|-----------|--------------|------------|------------|
| 24 KB (linear) | ~1-2 sec | ~2-3 sec | May fill buffer |
| 3.7 KB (arc) | ~0.2 sec | ~0.3 sec | Minimal buffer use |

### Execution Time
**Both modes produce identical execution times** - the machine still follows the same circular path at the same feed rate.

### Quality
- **Linear**: 36 facets per circle (visible under magnification)
- **Arc**: True circular interpolation (perfectly smooth)

## Compatibility

### Controllers That Support G2/G3
✅ Most modern CNC controllers, including:
- LinuxCNC
- Mach3/Mach4
- GRBL (v0.9+)
- Fanuc
- Haas
- Centroid
- PathPilot
- UCCNC
- TinyG
- Smoothieware

### When NOT to Use Arc Moves
❌ Very old controllers without arc support
❌ 3D printers with basic firmware (unless you know it supports arcs)
❌ Custom/unknown controllers - test first!

**Tip:** Most CNC mills from the last 20 years support arcs. When in doubt, test with a simple program first.

## Recommendations

### Use Arc Moves (`--use-arcs`) When:
✅ Your controller is from a major manufacturer (Fanuc, Haas, etc.)
✅ You're using LinuxCNC, Mach3/4, or GRBL
✅ You want the smallest possible files
✅ You want the smoothest circles
✅ You're transferring via slow connection (USB 1.1, serial)
✅ Your controller has limited memory

### Use Linear Segments (default) When:
✅ You're not sure if your controller supports arcs
✅ You're using a very old or custom controller
✅ File size doesn't matter
✅ You want maximum compatibility

## Testing Arc Support

Create a simple test file:
```gcode
G21 G90
G0 Z5.0
G0 X0 Y0
G1 Z-0.5 F50
G2 X0 Y0 I5.0 J0.0 F100
G0 Z5.0
M2
```

This draws a 10mm diameter circle. If your controller runs this without errors, arc moves are supported!

## Migration Guide

### If You're Currently Using Linear Mode
Simply add `--use-arcs` to your command:

**Before:**
```bash
python excellon_to_gcode.py board.drl -b 1.0 -d 2.0
```

**After:**
```bash
python excellon_to_gcode.py board.drl -b 1.0 -d 2.0 --use-arcs
```

That's it! Same result, much smaller file.

### Verifying Your Output
Always simulate first:
1. Load the G-code in CAMotics, OpenSCAM, or your CNC software simulator
2. Verify circles are smooth and complete
3. Check Z depths are correct
4. Run a test piece before production

## Advanced: I/J Offset Calculation

For those interested in the math:

```python
# Given:
hole_center_x = 50.0    # mm
hole_center_y = 50.0    # mm
mill_radius = 1.0       # mm (after accounting for bit radius)

# Current position (start of arc):
current_x = hole_center_x + mill_radius  # 51.0
current_y = hole_center_y                # 50.0

# Calculate I,J offsets to center:
i_offset = hole_center_x - current_x  # 50.0 - 51.0 = -1.0
j_offset = hole_center_y - current_y  # 50.0 - 50.0 = 0.0

# G-code:
G2 X51.0 Y50.0 Z-0.5 I-1.0 J0.0 F50.0
```

The controller calculates:
- Arc center = (current_x + I, current_y + J) = (51.0 + (-1.0), 50.0 + 0.0) = (50.0, 50.0) ✓
- Radius = sqrt(I² + J²) = sqrt(1.0² + 0.0²) = 1.0 mm ✓

## Conclusion

**Use `--use-arcs` for modern CNC controllers!**

Benefits:
- 85% smaller files
- Faster loading
- Smoother circles
- Less memory usage
- Same execution time
- Better surface finish

The only downside is potential incompatibility with very old controllers, which is rare.

---

**Happy milling with compact G-code!** 🎯
