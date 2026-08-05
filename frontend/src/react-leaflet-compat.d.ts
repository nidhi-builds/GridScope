// react-leaflet 5 references this non-exported core type in its declarations.
declare module "@react-leaflet/core/lib/context" {
  import type { Layer } from "leaflet";

  export type ControlledLayer = {
    addLayer(layer: Layer): void;
    removeLayer(layer: Layer): void;
  };
}
