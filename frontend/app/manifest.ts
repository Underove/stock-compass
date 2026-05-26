import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "NOVA",
    short_name: "NOVA",
    description: "AI가 주식 정보를 교차검증해 신뢰도를 알려주는 안전한 투자 길잡이",
    start_url: "/",
    display: "standalone",
    background_color: "#F2F2F7",
    theme_color: "#007AFF",
    orientation: "portrait",
    icons: [
      { src: "/icon", sizes: "512x512", type: "image/png" },
      { src: "/apple-icon", sizes: "180x180", type: "image/png" },
    ],
  };
}
