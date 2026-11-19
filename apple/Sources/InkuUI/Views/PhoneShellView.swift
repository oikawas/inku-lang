import SwiftUI

enum PhoneShellTab {
    static let creation = 0, library = 1, settings = 2, camera = 3
}

/// Retain the tab's views and their editing state while presenting the library as the root.
@MainActor
struct PhoneShellView<Creation: View, Library: View, Settings: View>: View {
    @Bindable var model: AppModel
    @Binding var tab: Int
    let runStatus: String
    let onHome: () -> Void
    @ViewBuilder let creation: () -> Creation
    @ViewBuilder let library: () -> Library
    @ViewBuilder let settings: () -> Settings

    var body: some View {
        TabView(selection: $tab) {
            NavigationStack {
                creation()
                    .toolbar {
                        ToolbarItem(placement: .navigation) {
                            Button(action: onHome) { Image(systemName: "chevron.left") }
                                .accessibilityLabel(model.display.webCopy("historyLibraryTitle", "ライブラリ"))
                        }
                    }
                    .inkuPhoneTabBarHidden()
            }
            .overlay(alignment: .leading) { PhoneBackEdge(action: onHome) }
            .inkuPhoneTabBarHidden()
            .tabItem { Label(model.display.localized("制作"), systemImage: "paintbrush") }.tag(PhoneShellTab.creation)
            library()
                .inkuPhoneTabBarHidden()
                .tabItem { Label(model.display.webCopy("historyLibraryTitle", "ライブラリ"), systemImage: "square.grid.3x3") }.tag(PhoneShellTab.library)
            settings()
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    if model.hasActiveRun {
                        PhoneRunStatusRow(model: model, status: runStatus) { tab = PhoneShellTab.creation }
                            .inkuPhoneFrontText(true, textScale: model.display.preferences.textScale)
                    }
                }
                .inkuPhoneTabBarHidden()
                .tabItem { Label(model.display.webCopy("settingsTitle", "設定"), systemImage: "gearshape") }.tag(PhoneShellTab.settings)
        }
    }
}

/// A narrow edge surface outside the padded page content, extending through the safe areas.
struct PhoneBackEdge: View {
    let action: () -> Void
    var body: some View {
        Color.clear.frame(width: 20).frame(maxHeight: .infinity)
            .contentShape(Rectangle()).ignoresSafeArea(edges: .vertical)
            .gesture(DragGesture(minimumDistance: 30).onEnded { value in
                if value.translation.width > 60 && abs(value.translation.height) < abs(value.translation.width) { action() }
            })
            .accessibilityHidden(true)
    }
}

@MainActor
struct PhoneRunStatusRow: View {
    @Bindable var model: AppModel
    let status: String
    let onOpen: () -> Void
    var body: some View {
        HStack(spacing: 10) {
            ProgressView().controlSize(.small)
            Text(status.isEmpty ? model.display.localized("描画中") : model.display.message(status))
                .inkuFont(12).fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
            Button(role: .destructive) { Task { await model.stopEveryRun() } } label: {
                Label(model.display.localized("停止"), systemImage: "stop.fill").inkuFont(12).frame(minWidth: 44, minHeight: 44)
            }.buttonStyle(.bordered).controlSize(.small)
        }
        .padding(.horizontal, 14).padding(.vertical, 8).background(InkuColor.bg)
        .contentShape(Rectangle()).onTapGesture(perform: onOpen)
    }
}
