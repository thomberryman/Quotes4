import path from "node:path";

import type { NextConfig } from "next";

type NextWebpackConfig = Exclude<NextConfig["webpack"], null | undefined>;

type ChunkAsset = {
  name: string;
  source: unknown;
};

type CompilationLike = {
  hooks: {
    processAssets: {
      tap(
        options: { name: string; stage: number },
        callback: () => void,
      ): void;
    };
  };
  getAssets(): ChunkAsset[];
  getAsset(name: string): ChunkAsset | undefined;
  emitAsset(name: string, source: unknown): void;
};

type CompilerLike = {
  webpack: {
    Compilation: {
      PROCESS_ASSETS_STAGE_ADDITIONS: number;
    };
  };
  hooks: {
    thisCompilation: {
      tap(
        name: string,
        callback: (compilation: CompilationLike) => void,
      ): void;
    };
  };
};

type WebpackPluginLike = {
  apply(compiler: CompilerLike): void;
};

type WebpackConfigLike = {
  plugins?: WebpackPluginLike[];
};

class MirrorServerChunkAssetsPlugin implements WebpackPluginLike {
  apply(compiler: CompilerLike) {
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
              compilation.emitAsset(mirroredName, asset.source);
            });
          },
        );
      },
    );
  }
}

function configureWebpack<T extends WebpackConfigLike>(
  config: T,
  { isServer }: { isServer: boolean },
): T {
  if (!isServer) {
    return config;
  }

  const plugins = config.plugins ? [...config.plugins] : [];
  plugins.push(new MirrorServerChunkAssetsPlugin());
  config.plugins = plugins;

  return config;
}

const nextConfig = {
  typedRoutes: false,
  transpilePackages: ["@quotes4/contracts", "@quotes4/domain"],
  webpack: configureWebpack as NextWebpackConfig,
} satisfies NextConfig;

export default nextConfig;
