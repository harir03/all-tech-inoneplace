# Vercel Design System & Guidelines

Based on [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md).

## 🎨 Design Philosophy
A developer-first brand aesthetic featuring stark monochromatic precision (pure blacks, crisp whites, and neutral grays) punctuated by vibrant multi-color gradient accents:
- **Develop**: `#0070f3` / `#00dfd8` (Cyan & Electric Blue)
- **Preview**: `#7928ca` / `#ff0080` (Violet & Hot Magenta)
- **Ship**: `#ff4d4d` / `#f9cb28` (Crimson & Amber)

## 🌌 Color Palette
```css
:root {
  /* Canvas & Grayscale */
  --geist-background: #000000;
  --geist-foreground: #ededed;
  --accents-1: #111111;
  --accents-2: #1a1a1a;
  --accents-3: #2e2e2e;
  --accents-4: #444444;
  --accents-5: #666666;
  --accents-6: #888888;
  --accents-7: #a1a1a1;
  --accents-8: #eaeaea;

  /* Brand / Vercel Gradients */
  --vercel-blue: #0070f3;
  --vercel-cyan: #50e3c2;
  --vercel-purple: #7928ca;
  --vercel-pink: #ff0080;
  --vercel-amber: #f5a623;
  --vercel-red: #ee0000;

  /* Gradients */
  --gradient-1: linear-gradient(135deg, #0070f3 0%, #50e3c2 100%);
  --gradient-2: linear-gradient(135deg, #7928ca 0%, #ff0080 100%);
  --gradient-3: linear-gradient(135deg, #ff4d4d 0%, #f9cb28 100%);
  --gradient-hero: radial-gradient(circle at 50% -20%, rgba(120, 119, 198, 0.25), rgba(255, 255, 255, 0));

  /* Borders & Shadows */
  --border-subtle: 1px solid rgba(255, 255, 255, 0.1);
  --border-card: 1px solid rgba(255, 255, 255, 0.14);
  --border-focus: 1px solid #0070f3;
  --shadow-subtle: 0 4px 20px rgba(0, 0, 0, 0.5);
  --shadow-hover: 0 12px 36px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(255, 255, 255, 0.2);
}
```

## 📐 Typography & Structure
- **Font Stack**: `Geist, Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
- **Monospace**: `Geist Mono, "SFMono-Regular", Menlo, Monaco, Consolas, monospace`
- **Radii**:
  - Small / Badge: `4px` - `6px`
  - Cards: `12px` - `14px`
  - Buttons / Pills: `100px` (Full Pill) or `8px` (Clean Rectangular)
