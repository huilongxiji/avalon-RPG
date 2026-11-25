import { writeFile } from 'node:fs/promises'
import openapiTS, { astToString } from 'openapi-typescript'
import { apiOrigin } from './backend.mjs'

const schema = new URL('/openapi.json', apiOrigin(process.env.NODE_ENV || 'development'))
const ast = await openapiTS(schema)
await writeFile(new URL('../src/api/schema.d.ts', import.meta.url), astToString(ast))
console.log('已更新 src/api/schema.d.ts')
