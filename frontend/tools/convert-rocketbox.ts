import * as T from "three";
import { FBXLoader } from "three/addons/loaders/FBXLoader.js";
import { GLTFExporter } from "three/addons/exporters/GLTFExporter.js";

const source = "/models/rocketbox-source/";
const variant =
  new URLSearchParams(location.search).get("variant") === "03" ? "03" : "02";
const output = document.querySelector<HTMLPreElement>("#status")!;
const manager = new T.LoadingManager();
manager.setURLModifier((url) => {
  if (url.startsWith("blob:") || url.startsWith("data:")) return url;
  const name = decodeURIComponent(
    url.replaceAll("\\", "/").split("/").pop()!,
  ).replace(/\.tga$/i, ".png");
  return source + name;
});
manager.addHandler(/\.tga$/i, new T.TextureLoader(manager));
const loader = new FBXLoader(manager);
const character = await loader.loadAsync(source + `Sports_Male_${variant}.fbx`);
const [idleSource, runSource] = await Promise.all([
  loader.loadAsync(source + "idle.fbx"),
  loader.loadAsync(source + "run.fbx"),
]);
const details: unknown[] = [];
character.traverse((node) => {
  if (node instanceof T.Mesh)
    details.push({
      mesh: node.name,
      vertices: node.geometry.attributes.position.count,
      materials: (Array.isArray(node.material)
        ? node.material
        : [node.material]
      ).map((m) => ({
        name: m.name,
        type: m.type,
        ...(m instanceof T.MeshPhongMaterial
          ? { map: !!m.map, normal: !!m.normalMap, opacity: m.opacity }
          : {}),
      })),
    });
});
output.textContent = JSON.stringify(
  {
    details,
    bounds: new T.Box3().setFromObject(character),
    bones: (() => {
      const b: string[] = [];
      character.traverse((n) => {
        if (n instanceof T.Bone) b.push(n.name);
      });
      return b;
    })(),
    idle: idleSource.animations.map((a) => ({
      name: a.name,
      tracks: a.tracks.slice(0, 10).map((t) => t.name),
    })),
    run: runSource.animations.map((a) => ({
      name: a.name,
      tracks: a.tracks.slice(0, 10).map((t) => t.name),
    })),
  },
  null,
  2,
);
// The first pass exposes model structure before conversion/export is enabled.
const button = document.querySelector<HTMLButtonElement>("#export")!;
button.disabled = false;
button.onclick = async () => {
  button.disabled = true;
  try {
    character.traverse((node) => {
      if (!(node instanceof T.Mesh)) return;
      // Retain only the highest authored LOD, including its skin and skeleton.
      if (/(midpoly|lowpoly|ultralowpoly)/i.test(node.name)) {
        node.visible = false;
        return;
      }
      const convert = (old: T.Material) => {
        if (!(old instanceof T.MeshPhongMaterial)) return old;
        const material = new T.MeshStandardMaterial({
          name: old.name,
          color: 0xffffff,
          map: old.map,
          normalMap: old.normalMap,
          roughness: 0.78,
          metalness: 0,
          alphaMap: old.alphaMap,
          alphaTest: old.transparent ? 0.45 : 0,
          side: old.side,
        });
        if (material.map) {
          material.map.colorSpace = T.SRGBColorSpace;
          material.map.userData.mimeType = "image/webp";
        }
        if (material.normalMap) material.normalScale.set(1, -1);
        return material;
      };
      node.material = Array.isArray(node.material)
        ? node.material.map(convert)
        : convert(node.material);
    });
    const clips = [
      idleSource.animations[0].clone(),
      runSource.animations[0].clone(),
    ];
    clips[0].name = "Idle";
    clips[1].name = "Run";
    // Retain each character's limb lengths; animation rotations come from the same rig family.
    const rootBone = character.getObjectByName("Bip01")!;
    for (const clip of clips) {
      clip.tracks = clip.tracks.filter((track) => {
        const [name, property] = track.name.split(".");
        return (
          !!character.getObjectByName(name) &&
          (property === "quaternion" ||
            (name === "Bip01" && property === "position"))
        );
      });
      for (const track of clip.tracks)
        if (track.name === "Bip01.position") {
          const originalY = track.values[1];
          for (let i = 0; i < track.values.length; i += 3) {
            track.values[i] = rootBone.position.x;
            track.values[i + 1] =
              rootBone.position.y + track.values[i + 1] - originalY;
            track.values[i + 2] = rootBone.position.z;
          }
        }
    }
    const glb = await new GLTFExporter().parseAsync(character, {
      binary: true,
      animations: clips,
      onlyVisible: true,
      maxTextureSize: 1024,
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(
      new Blob([glb as ArrayBuffer], { type: "model/gltf-binary" }),
    );
    link.download = `footballer-${variant}.glb`;
    link.click();
    output.textContent += "\nExport complete.";
  } catch (error) {
    output.textContent += "\nERROR: " + String(error);
  }
  button.disabled = false;
};
