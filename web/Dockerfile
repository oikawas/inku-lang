FROM node:22-bookworm-slim AS build
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
