import CoreGraphics
import Foundation
import InkuCore

enum ExportRaster {
    static let tileSide = 2048

    static func dimensions(svg: String, height: Int) throws -> (Int, Int) {
        try dimensions(scene: InkuCore.prepareSVG(svg: svg), height: height)
    }

    private static func dimensions(scene: PreparedSVG, height: Int) throws -> (Int, Int) {
        let widthValue = max(1, (scene.intrinsicWidth / scene.intrinsicHeight * Double(height)).rounded(.toNearestOrAwayFromZero))
        guard widthValue.isFinite, widthValue <= Double(Int32.max), height >= 1,
              widthValue * Double(height) <= Double(ExportService.maximumImagePixels) else {
            throw ExportFailure("用紙比率を保つと1画像の上限（1億4400万画素）を超えます。Y軸を小さくしてください。")
        }
        return (Int(widthValue), height)
    }

    static func image(svg: String, height: Int, forcedTileSide: Int? = nil) throws -> CGImage {
        try Task.checkCancellation()
        let scene = try InkuCore.prepareSVG(svg: svg)
        return try image(scene: scene, height: height, forcedTileSide: forcedTileSide)
    }

    private static func image(scene: PreparedSVG, height: Int, forcedTileSide: Int? = nil) throws -> CGImage {
        let (width, height) = try dimensions(scene: scene, height: height)
        if forcedTileSide == nil, max(width, height) <= 8192, width * height <= 16_777_216 {
            let raster = try scene.rasterize(targetHeight: UInt32(height))
            try Task.checkCancellation()
            guard let image = raster.makeCGImage() else { throw ExportFailure("描画画像を作れませんでした。") }
            return image
        }
        let context = try bitmap(width: width, height: height)
        let side = forcedTileSide ?? tileSide
        for y in stride(from: 0, to: height, by: side) {
            for x in stride(from: 0, to: width, by: side) {
                try Task.checkCancellation()
                let coreW = min(side, width - x), coreH = min(side, height - y)
                let raster = try scene.region(fullWidth: UInt32(width), fullHeight: UInt32(height), x: UInt32(x), y: UInt32(y), width: UInt32(coreW), height: UInt32(coreH))
                try Task.checkCancellation()
                guard let image = raster.makeCGImage() else { throw ExportFailure("画像タイルを作れませんでした。") }
                context.draw(image, in: CGRect(x: x, y: height - y - coreH, width: coreW, height: coreH))
            }
        }
        guard let result = context.makeImage() else { throw ExportFailure("書き出し画像を作れませんでした。") }
        return result
    }

    static func bitmap(width: Int, height: Int) throws -> CGContext {
        guard width > 0, height > 0, width <= ExportService.maximumImagePixels / height,
              let space = CGColorSpace(name: CGColorSpace.sRGB),
              let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
                                      space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else {
            throw ExportFailure("画像用のメモリを確保できませんでした。")
        }
        context.interpolationQuality = .high
        return context
    }

    static func onWhite(_ image: CGImage) throws -> CGImage {
        try Task.checkCancellation()
        let context = try bitmap(width: image.width, height: image.height)
        context.setFillColor(CGColor(gray: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: image.width, height: image.height))
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        guard let result = context.makeImage() else { throw ExportFailure("白背景の画像を作れませんでした。") }
        return result
    }

    static func fitted(svg: String, width: Int, height: Int) throws -> CGImage {
        try Task.checkCancellation()
        let scene = try InkuCore.prepareSVG(svg: svg)
        let intrinsicWidth = scene.intrinsicWidth / scene.intrinsicHeight * Double(height)
        let renderedHeight = intrinsicWidth > Double(width) ? max(1, Int((Double(height) * Double(width) / intrinsicWidth).rounded())) : height
        let image = try image(scene: scene, height: renderedHeight)
        let context = try bitmap(width: width, height: height)
        context.setFillColor(CGColor(gray: 1, alpha: 1)); context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        context.draw(image, in: CGRect(x: (width - image.width) / 2, y: (height - image.height) / 2, width: image.width, height: image.height))
        guard let result = context.makeImage() else { throw ExportFailure("アニメーション画像を作れませんでした。") }
        return result
    }
}
