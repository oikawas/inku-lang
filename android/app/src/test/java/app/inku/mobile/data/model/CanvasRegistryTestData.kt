package app.inku.mobile.data.model

internal const val CANVAS_REGISTRY_TEST_JSON =
    """{"registry":{"schema":"inku.canvas-format-registry.v1","formats":[{"id":"square","width_units":1,"height_units":1},{"id":"golden","width_units":809,"height_units":500},{"id":"a4","width_units":500,"height_units":707},{"id":"b4","width_units":500,"height_units":707},{"id":"pillar","width_units":1,"height_units":5},{"id":"oban","width_units":2,"height_units":3},{"id":"wide","width_units":47,"height_units":20},{"id":"byobu","width_units":11,"height_units":5},{"id":"vertical","width_units":9,"height_units":16},{"id":"sd_monitor","width_units":4,"height_units":3},{"id":"hd_monitor","width_units":16,"height_units":9}]},"digest":"0000000000000000000000000000000000000000000000000000000000000000"}"""

internal fun installCanvasRegistryForJvmTest() {
    CanvasAspects.installRegistry(CANVAS_REGISTRY_TEST_JSON)
}
