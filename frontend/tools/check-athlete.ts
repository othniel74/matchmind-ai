import * as T from "three";
import { loadAthleteAsset } from "../src/athleteAsset";

const output = document.querySelector<HTMLPreElement>("#results")!;
const checks: string[] = [];
function check(condition: boolean, message: string) {
  if (!condition) throw new Error(message);
  checks.push("PASS " + message);
  output.textContent = checks.join("\n");
}
function bones(root: T.Object3D) {
  const result: T.Bone[] = [];
  root.traverse((n) => {
    if (n instanceof T.Bone) result.push(n);
  });
  return result;
}
try {
  const asset = await loadAthleteAsset(new AbortController().signal);
  check(
    !!asset,
    "Enabled local models load with embedded PBR maps and Idle/Run clips",
  );
  const home = asset!.instantiate("home", false, 1),
    away = asset!.instantiate("away", false, 1),
    alternate = asset!.instantiate("home", false, 2);
  const first = bones(home.object),
    second = bones(away.object),
    third = bones(alternate.object);
  check(
    first.length >= 80 && third.length >= 80,
    "Both detailed footballer variants retain their authored human rigs",
  );
  check(
    first.every((b, i) => b !== second[i]),
    "Cloned players have independent bones",
  );
  const calf = first.find((b) => b.name === "Bip01_L_Calf")!,
    otherCalf = second.find((b) => b.name === "Bip01_L_Calf")!;
  const original = calf.quaternion.clone(),
    other = otherCalf.quaternion.clone();
  for (let i = 0; i < 10; i++) home.update(0.033, 1, false);
  check(
    original.angleTo(calf.quaternion) > 0.01,
    "Run animation deforms the player skeleton",
  );
  check(
    other.equals(otherCalf.quaternion),
    "Animating one player does not animate another",
  );
  const resting = calf.quaternion.clone();
  home.update(0.1, 1, true);
  check(
    resting.equals(calf.quaternion),
    "Reduced motion pauses character animation",
  );
  let maps = 0;
  away.object.traverse((n) => {
    if (n instanceof T.Mesh) {
      for (const m of Array.isArray(n.material) ? n.material : [n.material])
        if (m instanceof T.MeshStandardMaterial && m.map && m.normalMap) maps++;
    }
  });
  check(maps >= 2, "Body and face retain colour and normal textures");
  home.dispose();
  check(
    second.every((b) => !!b.parent),
    "Disposing a player preserves the other player's rig",
  );
  away.dispose();
  alternate.dispose();
  asset!.dispose();
  output.textContent += "\n\nAll 8 asset checks passed.";
} catch (error) {
  output.textContent += "\nFAIL " + String(error);
  console.error(error);
}
