# Detailed footballer integration

The studio now ships two free MIT-licensed Microsoft Rocketbox footballers instead of only procedural primitive figures. The source copyright notice and exact asset paths are included at `frontend/public/models/players/CREDITS.md`. No paid assets were purchased.

`footballer-02.glb` is approximately 4.95 MB and `footballer-03.glb` approximately 5.80 MB. Each includes textured skin/face/clothing, normal maps, an authored human skeleton and Idle/Run animation clips. The two source characters are alternated across each team; they are not 22 distinct identities. The source assets predate current cinematic character pipelines, so this is a substantial realism improvement rather than a claim of fully photorealistic rendering.

## Runtime

`src/athleteAsset.ts` validates same-origin GLB models, embedded skin rigs, textured PBR materials with normals, required clips and a triangle budget. It clones skeletons per player while sharing geometry and textures, blends in-place idle/run animation, preserves authored proportions, adapts fictional team colours and adds per-player shirt numbers. Materials and skeletons are disposed per instance; shared maps are released only when the asset set is disposed. Existing procedural figures remain the fallback if asset loading fails. The manifest controls activation and source attribution.

`src/HumanPlayers.tsx` renders the imported figures, field shadows and moving ball. Player detail offers a full-body inset and Face close-up. Reduced motion pauses animation, and full-time idle rendering settles then stops. Canonical event coordinates remain separate activity cues. Role-constrained 4-3-3 positions replace actor/recipient teleportation; a frame-rate-independent motion controller bounds acceleration, speed and turn rate. Goalkeepers face into the pitch even when retreating.

## Conversion and reproducibility

The original downloaded FBX/TGA inputs are retained locally under ignored `.asset-work/rocketbox`. Texture conversion to PNG preserves pixels. Temporary browser conversion inputs were moved to `.asset-work/rocketbox/converted-inputs` after export so they are excluded from the production build.

To repeat conversion, copy that input directory to `frontend/public/models/rocketbox-source`, run Vite, and open `/asset-converter.html?variant=02` or `?variant=03`. The development-only utility in `frontend/tools/convert-rocketbox.ts` applies FBX-to-PBR material conversion, removes missing-bone tracks, preserves rest translations and neutralizes horizontal root travel, then downloads a GLB. Place the outputs in `public/models/players` and remove the temporary public source directory before building. The HTML utilities are not Vite production entry points.

## Verification

Open `/asset-check.html` with the development server to exercise the actual shipping GLBs: required maps/clips, both variants' rigs, independent skeleton clones, run deformation, animation isolation, reduced-motion pause and safe per-instance disposal. The check utility is in `frontend/tools/check-athlete.ts`.

Production validation: `npm run build`. Browser visual QA covers both live replay and full-time poses, distinct team colours, expanded preview and body/face detail. The optional Three.js chunk continues to produce Vite's size advisory; it is loaded separately from the main app.

Movement regression checks: `node --experimental-strip-types tools/check-pitch-motion.ts` from frontend, plus `pytest tests/test_pitch.py` from backend. These cover target reversals, bounded speed/acceleration/turns, goalkeeper facing and confinement, full-time braking, reduced motion, causal team shape and preserved event evidence.
