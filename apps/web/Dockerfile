FROM node:22-alpine

WORKDIR /workspace

COPY package.json package-lock.json tsconfig.base.json tsconfig.json eslint.config.mjs ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
COPY packages/domain/package.json packages/domain/package.json

RUN npm install

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev:web"]
