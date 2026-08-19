# The build stage runs on the machine doing the building, never on the target
# platform: vite/rollup under QEMU hung for 5h58m in `rendering chunks...` on
# the arm64 leg of release run 32092151332 and was cancelled at the 6h job
# limit, while the amd64 leg finished the same step in 14.4s. Nothing here is
# architecture-specific -- the app declares no runtime dependencies and
# adapter-node emits plain JS -- so the bundle built on one arch is the
# bundle the other arch runs. The runtime stage below stays on the target
# platform, which is where the node binary that actually ships comes from.
FROM --platform=$BUILDPLATFORM node:22-bookworm-slim AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM node:22-bookworm-slim AS runtime
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=5173
WORKDIR /app
COPY --from=build /app/build ./build
COPY --from=build /app/package.json /app/package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
USER node
EXPOSE 5173
CMD ["node", "build"]
