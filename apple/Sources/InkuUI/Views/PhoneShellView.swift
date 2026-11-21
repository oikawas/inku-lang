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
                    VStack(spacing: 0) {
                        if let completion = model.phoneCompletion {
                            PhoneDrawingCompletionRow(display: model.display) {
                                tab = PhoneShellTab.library
                                model.phoneWorkToView = completion.id
                            }
                        }
                        if model.phoneProgressIsActive {
                            PhoneRunStatusRow(model: model, status: runStatus) {
                                if let wait = model.phoneDrawingWait, wait.running {
                                    tab = PhoneShellTab.library
                                    wait.visible = true
                                } else {
                                    tab = PhoneShellTab.creation
                                }
                            }
                        }
                    }
                    .inkuPhoneFrontText(true, textScale: model.display.preferences.textScale)
                }
                .inkuPhoneTabBarHidden()
                .tabItem { Label(model.display.webCopy("settingsTitle", "設定"), systemImage: "gearshape") }.tag(PhoneShellTab.settings)
        }
        .onChange(of: tab) { _, tab in
            if tab != PhoneShellTab.library, let wait = model.phoneDrawingWait, wait.visible {
                model.leavePhoneDrawingWait(wait)
            }
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
    var mascot = false
    let onOpen: () -> Void
    var body: some View {
        HStack(spacing: 10) {
            Button(action: onOpen) {
                HStack(spacing: 10) {
                    if mascot {
                        let kind = model.display.preferences.mascot == "yuragi" ? "yuragi" : "incu"
                        MascotView(kind: kind, accessibilityText: model.display.localized(kind == "yuragi" ? "Yuragiが描画中" : "Incuが描画中"))
                    } else {
                        ProgressView().controlSize(.small)
                    }
                    Text(status.isEmpty ? model.display.localized("描画中") : model.display.message(status))
                        .inkuFont(12).fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                }.frame(minHeight: 44).contentShape(Rectangle())
            }.buttonStyle(.plain)
            Button(role: .destructive) {
                Task {
                    if model.phoneDrawingWait?.running == true { await model.stopPhoneDrawing() }
                    else { await model.stopEveryRun() }
                }
            } label: {
                Label(model.display.localized("停止"), systemImage: "stop.fill").inkuFont(12).frame(minWidth: 44, minHeight: 44)
            }.buttonStyle(.bordered).controlSize(.small)
        }
        .padding(.horizontal, 14).padding(.vertical, 8).background(InkuColor.bg)
    }
}
