# Third-party software

The independent npm lock pins Three.js, three-bvh-csg and three-mesh-bvh (MIT). The adapter's independent Cargo lock records the Rust and wasm-bindgen dependencies and the two local core crates.

`npm run build:wasm` collects the original license texts from the installed runtime npm packages and Cargo packages, with package/version/license headings, into `public/THIRD_PARTY_NOTICES.txt`. Vite copies this file into the static distribution. Distribute that file alongside the JavaScript and WASM. Missing license texts stop the build.

Primary API references: [OrbitControls](https://threejs.org/docs/pages/OrbitControls.html), [GLTFExporter](https://threejs.org/docs/pages/GLTFExporter.html), [three-bvh-csg](https://github.com/gkjohnson/three-bvh-csg).
