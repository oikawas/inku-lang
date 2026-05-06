package app.inku.mobile

import android.app.Application
import app.inku.mobile.data.db.InkuDatabase

class InkuApplication : Application() {
    val database: InkuDatabase by lazy {
        InkuDatabase.open(this)
    }
}
