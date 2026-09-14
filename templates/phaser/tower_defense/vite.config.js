import { defineConfig } from 'vite';
import tailwind from 'tailwindcss';
export default defineConfig({base:'./',css:{postcss:{plugins:[tailwind({content:['./src/**/*.ts']})]}},build:{assetsInlineLimit:0}});
