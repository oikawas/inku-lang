#if os(iOS)
import ImageIO
import SwiftUI
import UIKit
import UniformTypeIdentifiers

/// The image tab's "Take photo" (iOS plan §3 #22, author's ruling 4): the photo goes the same way as one chosen from
/// Photos or Files (the shared core's "draw from an image"). It is handed over as JPEG with the camera's metadata
/// (Exif and orientation), as a photo from Photos keeps its Exif. Hidden where there is no camera (the simulator).
struct InkuCameraButton: View {
    let title: String
    let disabled: Bool
    let onCapture: (Data) -> Void
    @State private var capturing = false

    var body: some View {
        if UIImagePickerController.isSourceTypeAvailable(.camera) {
            Button(title) { capturing = true }
                .buttonStyle(InkuGhostButtonStyle())
                .disabled(disabled)
                .fullScreenCover(isPresented: $capturing) {
                    InkuCameraPicker { data in
                        capturing = false
                        if let data { onCapture(data) }
                    }.ignoresSafeArea()
                }
        }
    }
}

private struct InkuCameraPicker: UIViewControllerRepresentable {
    let onFinish: (Data?) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onFinish: onFinish) }
    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.cameraCaptureMode = .photo
        picker.mediaTypes = [UTType.image.identifier]
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ picker: UIImagePickerController, context: Context) {}

    @MainActor final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let onFinish: (Data?) -> Void
        init(onFinish: @escaping (Data?) -> Void) { self.onFinish = onFinish }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            guard let image = info[.originalImage] as? UIImage, let cgImage = image.cgImage else {
                InkuFeedback.beep(); onFinish(nil); return
            }
            let metadata = info[.mediaMetadata] as? [String: Any] ?? [:]
            onFinish(Self.jpeg(cgImage, metadata: metadata))
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { onFinish(nil) }

        /// The sensor's pixels with the camera's metadata: its orientation tag says how to turn them, as in a photo
        /// saved by the Camera app.
        static func jpeg(_ image: CGImage, metadata: [String: Any]) -> Data? {
            let data = NSMutableData()
            guard let destination = CGImageDestinationCreateWithData(data, UTType.jpeg.identifier as CFString, 1, nil) else { return nil }
            var properties = metadata
            properties[kCGImageDestinationLossyCompressionQuality as String] = 0.92
            CGImageDestinationAddImage(destination, image, properties as CFDictionary)
            return CGImageDestinationFinalize(destination) ? data as Data : nil
        }
    }
}
#endif
