import InkuPersistence
import SwiftUI
#if os(macOS)
import AppKit
#endif

extension Ddl3DInstallation {
    /// The 3D switch shows only with a registered viewer on a platform that hosts it (the macOS web view).
    static var available: Bool {
        #if os(macOS)
        registered != nil
        #else
        false
        #endif
    }
}

/// Web `Ddl3DModeSwitch.svelte`: immediately left of the hash button, it names where it goes, 3D in 2D and 2D in 3D.
struct Ddl3DModeButton: View {
    let display: DisplaySettings
    @Binding var threeDimensional: Bool

    var body: some View {
        Button { threeDimensional.toggle() } label: { Text(threeDimensional ? "2D" : "3D") }
            .buttonStyle(Ddl3DModeButtonStyle(active: threeDimensional))
            .accessibilityLabel(display.webCopy("ddl3dMode", "2D / 3D表示"))
            .accessibilityAddTraits(threeDimensional ? .isSelected : [])
            .inkuTooltip(threeDimensional ? display.tooltip("2Dに戻る", serverKey: "ddl3dReturn") : display.tooltip("3D表示（実験）", serverKey: "ddl3dTitle"))
    }
}

/// Web `.canvas-mode-button`: 40×34 at least, the small button's padding and radius, semibold; the accent while in 3D.
struct Ddl3DModeButtonStyle: ButtonStyle {
    var active: Bool
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .inkuFont(12, weight: .semibold)
            .lineLimit(1)
            .padding(.horizontal, 10).padding(.vertical, 4)
            .frame(minWidth: 40, minHeight: 34)
            .foregroundStyle(active ? Color.white : Color.primary)
            .background(RoundedRectangle(cornerRadius: 4, style: .continuous)
                .fill(active ? Color.accentColor : configuration.isPressed ? InkuColor.panel : InkuColor.floating))
            .overlay(RoundedRectangle(cornerRadius: 4, style: .continuous).stroke(active ? Color.accentColor : InkuColor.border2))
            .shadow(color: .black.opacity(0.1), radius: 3, y: 1)
            .opacity(isEnabled ? 1 : 0.8)
            .contentShape(Rectangle())
    }
}

extension WorkspaceUIState {
    /// Web `canvasAreaEl.requestFullscreen()` for the 3D view: only the canvas area, in a full-screen window.
    func toggleCanvasFullScreen() {
        if canvasFullScreen { exitCanvasFullScreen() } else { enterCanvasFullScreen() }
    }

    func enterCanvasFullScreen() {
        guard !canvasFullScreen else { return }
        #if os(macOS)
        let window = NSApp.keyWindow
        canvasFullScreenWindow = window
        canvasFullScreenKeepsWindow = window?.styleMask.contains(.fullScreen) == true
        if !canvasFullScreenKeepsWindow { window?.toggleFullScreen(nil) }
        #endif
        canvasFullScreen = true
    }

    /// Leaves the canvas full screen, and the window's too unless the window was already full screen.
    func exitCanvasFullScreen() {
        guard canvasFullScreen else { return }
        canvasFullScreen = false
        #if os(macOS)
        if !canvasFullScreenKeepsWindow, let window = canvasFullScreenWindow, window.styleMask.contains(.fullScreen) {
            window.toggleFullScreen(nil)
        }
        canvasFullScreenWindow = nil
        #endif
    }
}

#if os(macOS)
/// Web `Ddl3DHost.svelte`'s markup over the viewer: the preparing note at the top left with a way back, and the
/// failure covering the view with retry, return to 2D and the reason under a details disclosure.
struct Ddl3DCanvas: View {
    let controller: Ddl3DController
    let registration: Ddl3DInstallation.Registered
    let work: SavedWork
    let initialView: Ddl3DInitialView
    let onReturn: () -> Void
    let onEscape: () -> Bool
    @Environment(DisplaySettings.self) private var display
    @Environment(\.colorScheme) private var colorScheme

    private struct InputKey: Equatable { let work: SavedWork; let language: String }

    var body: some View {
        ZStack(alignment: .topLeading) {
            InkuColor.bg
            Ddl3DSurface(controller: controller, registration: registration,
                         title: display.webCopy("ddl3dTitle", "3D表示（実験）"), onEscape: onEscape)
                // Web `inert` while the failure covers the view.
                .allowsHitTesting(controller.failure == nil)
                .accessibilityHidden(controller.failure != nil)
            if let failure = controller.failure {
                failureView(failure)
            } else if controller.preparing {
                preparingView.padding(8)
            }
        }
        .onChange(of: InputKey(work: work, language: display.preferences.language), initial: true) { _, key in
            // The 2D canvas as it stands for this work, whichever change SwiftUI reports first.
            controller.initialView = initialView
            controller.update(input: Result { () throws(Ddl3DInputError) in try Ddl3DInput.snapshot(key.work) }, locale: key.language)
        }
        .onChange(of: initialView, initial: true) { _, view in controller.initialView = view }
        .onChange(of: colorScheme, initial: true) { _, scheme in controller.theme = scheme == .dark ? "dark" : "light" }
        .onAppear { controller.onReturn = onReturn }
    }

    private var preparingView: some View {
        HStack(spacing: 8) {
            Text(display.webCopy("ddl3dPreparing", "3Dを準備中…")).inkuFont(12)
            Button(display.webCopy("ddl3dReturn", "2Dに戻る"), action: onReturn).buttonStyle(InkuGhostButtonStyle())
        }
        .padding(8)
        .background(InkuColor.bg, in: RoundedRectangle(cornerRadius: 4, style: .continuous))
        .accessibilityElement(children: .contain)
    }

    private func failureView(_ failure: String) -> some View {
        VStack(spacing: 12) {
            Text(display.webCopy("ddl3dFailed", "この作品を3Dで表示できません。2Dで閲覧を続けられます。"))
                .inkuFont(13).multilineTextAlignment(.center)
            DisclosureGroup(display.webCopy("ddl3dDetails", "詳細")) {
                Text(failure).inkuFont(12, design: .monospaced).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 4)
            }
            .inkuFont(12)
            .frame(maxWidth: 390)
            HStack(spacing: 8) {
                Button(display.webCopy("ddl3dRetry", "再試行")) { controller.retry() }
                Button(display.webCopy("ddl3dReturn", "2Dに戻る"), action: onReturn)
            }
            .buttonStyle(InkuGhostButtonStyle())
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(InkuColor.bg)
        .accessibilityElement(children: .contain)
    }
}
#endif
