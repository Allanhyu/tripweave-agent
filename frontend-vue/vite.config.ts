import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [vue()],
    server: {
      host: env.VITE_DEV_HOST || "127.0.0.1",
      port: Number(env.VITE_DEV_PORT || 5190),
    },
    preview: {
      host: env.VITE_PREVIEW_HOST || "127.0.0.1",
      port: Number(env.VITE_PREVIEW_PORT || 5191),
    },
  };
});
