import * as T from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";

export type AthleteManifest = {
  enabled: boolean;
  url: string;
  variants?: string[];
  rocketboxKit?: boolean;
  credit: string;
  license: string;
  forwardRotation: number;
  jerseyMaterials: string[];
  shortsMaterials: string[];
  clips: { idle: string; run: string };
};
export type ImportedAthlete = {
  object: T.Group;
  update: (dt: number, speed: number, reduced: boolean, kick?: number) => void;
  dispose: () => void;
};

/** Preserve authored PBR maps; only explicitly named kit materials receive tint. */
export async function loadAthleteAsset(
  signal: AbortSignal,
  manifestPath = "/models/players/manifest.json",
) {
  const response = await fetch(manifestPath, { signal });
  if (!response.ok) throw new Error("Player asset manifest is unavailable.");
  const config = (await response.json()) as AthleteManifest;
  if (!config.enabled) return null;
  if (!config.credit || !config.license)
    throw new Error("Player asset provenance is missing.");
  const results = await Promise.allSettled(
    (config.variants?.length ? config.variants : [config.url]).map((url) =>
      loadTemplate({ ...config, url }, signal),
    ),
  );
  const templates = results
    .filter(
      (
        r,
      ): r is PromiseFulfilledResult<
        Awaited<ReturnType<typeof loadTemplate>>
      > => r.status === "fulfilled",
    )
    .map((r) => r.value)
    .filter((t) => t !== null);
  const failure = results.find((r) => r.status === "rejected");
  if (signal.aborted || failure) {
    templates.forEach((t) => t.dispose());
    if (failure?.status === "rejected") throw failure.reason;
    return null;
  }
  return {
    dispose: () => templates.forEach((t) => t.dispose()),
    instantiate: (team: string, keeper: boolean, number = 1) =>
      templates[(number - 1) % templates.length].instantiate(
        team,
        keeper,
        number,
      ),
  };
}

async function loadTemplate(config: AthleteManifest, signal: AbortSignal) {
  const url = new URL(config.url, window.location.origin);
  if (url.origin !== window.location.origin || !url.pathname.endsWith(".glb"))
    throw new Error("Player assets must be locally hosted GLB files.");
  const manager = new T.LoadingManager();
  manager.setURLModifier((resource) => {
    const resolved = new URL(resource, window.location.origin);
    if (
      resolved.origin !== window.location.origin &&
      !resource.startsWith("blob:") &&
      !resource.startsWith("data:")
    )
      throw new Error("Player models cannot load external resources.");
    return resource;
  });
  const model = await new GLTFLoader(manager).loadAsync(url.href);
  const geometries = new Set<T.BufferGeometry>();
  const materials = new Set<T.Material>();
  const textures = new Set<T.Texture>();
  const skeletons = new Set<T.Skeleton>();
  let skinned = 0,
    triangles = 0,
    hasPBR = false;
  model.scene.traverse((node) => {
    if (!(node instanceof T.Mesh)) return;
    geometries.add(node.geometry);
    triangles +=
      (node.geometry.index?.count ??
        node.geometry.attributes.position?.count ??
        0) / 3;
    if (node instanceof T.SkinnedMesh) {
      skinned++;
      skeletons.add(node.skeleton);
    }
    for (const material of Array.isArray(node.material)
      ? node.material
      : [node.material]) {
      materials.add(material);
      if (
        material instanceof T.MeshStandardMaterial &&
        material.map &&
        material.normalMap
      )
        hasPBR = true;
      for (const value of Object.values(material))
        if (value instanceof T.Texture) textures.add(value);
    }
  });
  const labelCanvas = document.createElement("canvas");
  labelCanvas.width = 704;
  labelCanvas.height = 96;
  const labelContext = labelCanvas.getContext("2d")!;
  labelContext.fillStyle = "#ffffff";
  labelContext.font = "bold 66px Arial";
  labelContext.textAlign = "center";
  labelContext.textBaseline = "middle";
  for (let n = 1; n <= 11; n++)
    labelContext.fillText(String(n), (n - 0.5) * 64, 48);
  const numberAtlas = new T.CanvasTexture(labelCanvas);
  textures.add(numberAtlas);
  const dispose = () => {
    geometries.forEach((g) => g.dispose());
    materials.forEach((m) => m.dispose());
    textures.forEach((t) => {
      t.dispose();
      if (t.image instanceof ImageBitmap) t.image.close();
    });
    skeletons.forEach((s) => s.dispose());
  };
  const idle = T.AnimationClip.findByName(
    model.animations,
    config.clips?.idle ?? "Idle",
  );
  const run = T.AnimationClip.findByName(
    model.animations,
    config.clips?.run ?? "Run",
  );
  if (
    signal.aborted ||
    !skinned ||
    !hasPBR ||
    triangles > 60000 ||
    !idle ||
    !run
  ) {
    dispose();
    if (signal.aborted) return null;
    throw new Error(
      "Player GLB needs a skin rig, textured PBR materials with normal maps, Idle/Run clips and at most 60,000 triangles.",
    );
  }
  const bounds = new T.Box3().setFromObject(model.scene);
  const dimensions = bounds.getSize(new T.Vector3());
  if (!Number.isFinite(dimensions.y) || dimensions.y <= 0) {
    dispose();
    throw new Error("Invalid player model dimensions.");
  }
  const center = bounds.getCenter(new T.Vector3());
  return {
    dispose,
    instantiate(team: string, keeper: boolean, number = 1): ImportedAthlete {
      const object = new T.Group();
      const normalization = new T.Group();
      object.add(normalization);
      normalization.scale.setScalar(1.95 / dimensions.y);
      normalization.rotation.y = Number.isFinite(config.forwardRotation)
        ? config.forwardRotation
        : 0;
      const character = clone(model.scene);
      const offset = new T.Group();
      offset.position.set(-center.x, -bounds.min.y, -center.z);
      offset.add(character);
      normalization.add(offset);
      const instanceMaterials = new Set<T.Material>();
      const instanceSkeletons = new Set<T.Skeleton>();
      const kit = keeper
        ? team === "home"
          ? "#dac45a"
          : "#ae8ec8"
        : team === "home"
          ? "#eceee5"
          : "#77b7dd";
      character.traverse((node) => {
        if (!(node instanceof T.Mesh)) return;
        node.castShadow = true;
        node.receiveShadow = true;
        const copy = (material: T.Material) => {
          const result = material.clone();
          instanceMaterials.add(result);
          if (result instanceof T.MeshStandardMaterial) {
            if (
              config.jerseyMaterials?.includes(material.name) &&
              !config.rocketboxKit
            )
              result.color.set(kit);
            if (config.shortsMaterials?.includes(material.name))
              result.color.set(team === "home" ? "#1e2d39" : "#eef0f1");
            if (config.rocketboxKit && /_body$/.test(material.name)) {
              const kitColor = new T.Color(kit),
                shortColor = new T.Color(
                  team === "home" ? "#1e2d39" : "#e7ebef",
                );
              result.onBeforeCompile = (shader) => {
                shader.uniforms.demoKit = { value: kitColor };
                shader.uniforms.demoShorts = { value: shortColor };
                shader.uniforms.jerseyNumbers = { value: numberAtlas };
                shader.uniforms.jerseyIndex = { value: number - 1 };
                shader.uniforms.jerseyInk = {
                  value: new T.Color(team === "home" ? "#132738" : "#f2f5ed"),
                };
                shader.vertexShader =
                  "varying vec3 vKitRest;\n" +
                  shader.vertexShader.replace(
                    "#include <begin_vertex>",
                    "#include <begin_vertex>\nvKitRest=position;",
                  );
                shader.fragmentShader =
                  "varying vec3 vKitRest;\nuniform vec3 demoKit;\nuniform vec3 demoShorts;\nuniform sampler2D jerseyNumbers;\nuniform float jerseyIndex;\nuniform vec3 jerseyInk;\n" +
                  shader.fragmentShader.replace(
                    "#include <map_fragment>",
                    `#include <map_fragment>
                  float height=vKitRest.z;
                  bool skin=diffuseColor.r>diffuseColor.g*1.08 && diffuseColor.r>diffuseColor.b*1.16;
                  bool shirt=height>99.0 && height<149.0 && abs(vKitRest.x)<36.0;
                  bool shorts=height>73.0 && height<99.0;
                  bool socks=height>17.0 && height<51.0;
                  if(!skin && (shirt || shorts || socks)) {
                    float fabric=dot(diffuseColor.rgb,vec3(.2126,.7152,.0722));
                    diffuseColor.rgb=(shorts ? demoShorts : demoKit)*(.72+.28*fabric);
                    if(shirt && height>117.0 && height<137.0 && abs(vKitRest.x)<9.0 && abs(vKitRest.y)>7.0) {
                      float numberX=(vKitRest.y<0.0 ? vKitRest.x : -vKitRest.x)/18.0+.5;
                      vec2 printUV=vec2((jerseyIndex+numberX)/11.0,(height-117.0)/20.0);
                      diffuseColor.rgb=mix(diffuseColor.rgb,jerseyInk,texture2D(jerseyNumbers,printUV).a);
                    }
                  }
                `,
                  );
              };
              result.customProgramCacheKey = () => "rocketbox-kit-v2";
            }
          }
          return result;
        };
        node.material = Array.isArray(node.material)
          ? node.material.map(copy)
          : copy(node.material);
        if (node instanceof T.SkinnedMesh) instanceSkeletons.add(node.skeleton);
      });
      const mixer = new T.AnimationMixer(character);
      const standing = mixer.clipAction(idle).play();
      const running = mixer.clipAction(run).play();
      standing.setEffectiveWeight(1);
      running.setEffectiveWeight(0);
      mixer.update(0);
      let blend = 0;
      return {
        object,
        update(dt, speed, reduced, kick = 0) {
          const desired = reduced ? 0 : T.MathUtils.clamp(speed, 0, 1);
          blend = T.MathUtils.lerp(blend, desired, 1 - Math.exp(-dt * 8));
          standing.setEffectiveWeight(1 - blend);
          running.setEffectiveWeight(blend);
          running.setEffectiveTimeScale(0.75 + blend * 0.6);
          if (!reduced) mixer.update(dt);
          if (!reduced && kick > 0) {
            object.updateWorldMatrix(true, true);
            const thigh = character.getObjectByName("Bip01_R_Thigh");
            if (thigh) {
              const axis = new T.Vector3(1, 0, 0)
                .applyQuaternion(object.getWorldQuaternion(new T.Quaternion()))
                .applyQuaternion(
                  thigh.getWorldQuaternion(new T.Quaternion()).invert(),
                );
              thigh.rotateOnAxis(axis, -kick * 0.8);
            }
          }
        },
        dispose() {
          mixer.stopAllAction();
          mixer.uncacheRoot(character);
          instanceMaterials.forEach((m) => m.dispose());
          instanceSkeletons.forEach((s) => s.dispose());
          object.removeFromParent();
        },
      };
    },
  };
}
