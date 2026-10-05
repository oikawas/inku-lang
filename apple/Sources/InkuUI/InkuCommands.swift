import SwiftUI

/// Scene-owned actions keep menus aligned with the active work and selection.
public enum InkuCommandAction: Hashable, Sendable {
    case newWork, openDDL, settings
    case creation, library, lineage, automation, drawingLogs
    case export, copyImage, presentation
}

public struct InkuCommandContext {
    public let enabledActions: Set<InkuCommandAction>
    private let handler: @MainActor (InkuCommandAction) -> Void

    public init(
        enabledActions: Set<InkuCommandAction>,
        perform: @escaping @MainActor (InkuCommandAction) -> Void
    ) {
        self.enabledActions = enabledActions
        handler = perform
    }

    public func isEnabled(_ action: InkuCommandAction) -> Bool {
        enabledActions.contains(action)
    }

    @MainActor public func perform(_ action: InkuCommandAction) {
        guard isEnabled(action) else { return }
        handler(action)
    }
}

private struct InkuCommandContextKey: FocusedValueKey {
    typealias Value = InkuCommandContext
}

public extension FocusedValues {
    var inkuCommandContext: InkuCommandContext? {
        get { self[InkuCommandContextKey.self] }
        set { self[InkuCommandContextKey.self] = newValue }
    }
}

/// Publish a context with focusedSceneValue from the root of each app window.
@MainActor
public struct InkuCommands: Commands {
    @FocusedValue(\.inkuCommandContext) private var context
    @Bindable private var display: DisplaySettings
    #if os(macOS)
    @Environment(\.openWindow) private var openWindow
    #endif

    public init(display: DisplaySettings) { self.display = display }

    public var body: some Commands {
        #if os(macOS)
        CommandGroup(replacing: .appInfo) {
            Button(display.localized("inkuについて")) { openWindow(id: "about") }
        }
        #endif
        CommandGroup(replacing: .appSettings) {
            actionButton("設定…", action: .settings)
                .keyboardShortcut(",", modifiers: .command)
        }
        CommandGroup(replacing: .newItem) {
            actionButton("新規制作", action: .newWork)
                .keyboardShortcut("n", modifiers: .command)
            actionButton("DDLファイルを読み込む…", action: .openDDL)
                .keyboardShortcut("o", modifiers: .command)
        }
        CommandGroup(replacing: .importExport) {
            actionButton("書き出す…", action: .export)
                .keyboardShortcut("e", modifiers: [.command, .shift])
        }
        CommandMenu(Text(display.localized("作品"))) {
            actionButton("画像をコピー", action: .copyImage)
                .keyboardShortcut("c", modifiers: [.command, .shift])
            actionButton("全画面で表示", action: .presentation)
        }
        // Library opens over the window, lineage is the workspace tab, demo is a settings page (Web AppRail).
        CommandMenu(Text(display.localized("移動"))) {
            actionButton("制作", action: .creation)
                .keyboardShortcut("1", modifiers: .command)
            actionButton("ライブラリ", action: .library)
                .keyboardShortcut("2", modifiers: .command)
            actionButton("系譜", action: .lineage)
                .keyboardShortcut("3", modifiers: .command)
            actionButton("デモ", action: .automation)
                .keyboardShortcut("4", modifiers: .command)
            Divider()
            actionButton("描画ログ", action: .drawingLogs)
                .keyboardShortcut("l", modifiers: [.command, .shift])
        }
    }

    private func actionButton(_ title: String, action: InkuCommandAction) -> some View {
        Button(display.localized(title)) { context?.perform(action) }
            .disabled(context?.isEnabled(action) != true)
    }
}
