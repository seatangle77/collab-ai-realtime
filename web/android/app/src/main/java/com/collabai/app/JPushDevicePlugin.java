package com.collabai.app;

import cn.jpush.android.api.JPushInterface;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "JPushDevice")
public class JPushDevicePlugin extends Plugin {
    @PluginMethod
    public void getRegistrationId(PluginCall call) {
        String registrationId = JPushInterface.getRegistrationID(getContext());
        JSObject result = new JSObject();
        result.put("deviceToken", registrationId == null ? "" : registrationId);
        call.resolve(result);
    }
}
