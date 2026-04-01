import path from "node:path";

import type { NextConfig } from "next";
import type { Compiler, Configuration, sources, WebpackPluginInstance } from "webpack";

class MirrorServerChunkAssetsPlugin implements WebpackPluginInstance {
  apply(compiler: Compiler) {
    const { Compilation } = compiler.webpack;

    compiler.hooks.thisCompilation.tap(
      "MirrorServerChunkAssetsPlugin",
      (compilation) => {
        compilation.hooks.processAssets.tap(
          {
            name: "MirrorServerChunkAssetsPlugin",
            stage: Compilation.PROCESS_ASSETS_STAGE_ADDITIONS,
          },
          () => {
            compilation.getAssets().forEach((asset) => {
              if (!asset.name.startsWith("chunks/") || !asset.name.endsWith(".js")) {
                return;
              }

              const mirroredName = path.posix.basename(asset.name);
              if (compilation.getAsset(mirroredName)) {
                return;
              }

              // Next's server runtime requires sibling chunk files from `.next/server`.
              // Mirror chunk assets into the server root so page-data collection can load them.
              compilation.emitAsset(
                mirroredName,
                asset.source as sources.Source,
              );
            });
          },
        );
      },
    );
  }
}

const nextConfig: NextConfig = {
  typedRoutes: false,
  transpilePackages: ["@quotes4/contracts", "@quotes4/domain"],
  webpack: (config: Configuration, { isServer }) => {
    if (isServer) {
      const plugins = config.plugins ?? [];
      plugins.push(new MirrorServerChunkAssetsPlugin());
      config.plugins = plugins;
    }

    return config;
  },
};

export default nextConfig;
