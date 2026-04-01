// ========== htmlbSubmitLib ==========
function htmlbSubmitLib(library,elem,eventType,formID,objectID,eventName,paramCount,param1,param2,param3,param4,param5,param6,param7,param8,param9)
{
  /*if((typeof(eventName) != "undefined") && eventName.length>0 && eventName.indexOf("-") > -1)
  {
    window.top.WCF_CurrentLogicalLink = eventName;
  }*/
  document.forms[formID].onInputProcessing.value = library;
  htmlbSubmit(elem,eventType,formID,objectID,eventName,paramCount,param1,param2,param3,param4,param5,param6,param7,param8,param9);
}

// ========== htmlbSubmitFormAjax ==========
function htmlbSubmitFormAjax(form)
{

var returnvalue = false;
if (isAjaxEnabled == true && ajax_submit == true)
{
ajax_submit = false;
var str = "";
if (bindOnlyEvent == false)
{

str = createFormInputString(form);

}
else
{

str = bindHtmlbEvent(form);

var targetValues = document.getElementById("sap-ajaxtarget");
if (targetValues)
{
str = str + "&sap-ajaxtarget=" + targetValues.value;
}
var modeValue = document.getElementById("sap-ajax_dh_mode");
if (modeValue != null)
{
str = str + "&sap-ajax_dh_mode=" + modeValue.value;
}

}

clearAjaxRequestOptions();

if (str != null)
{

str = str + "&sap-ajax_request=X";

var elementid = getElementIdToReplace(form);

if (elementid != null)
{
var ajaxObj = null;
try
{

ajaxObj = new AjaxRequest(form.action, {
method: 'post',
asynchronous: true,
parameters: str,
bindingMode: 'xml',
onComplete: deltaRenderingCallback,
submittedFormId: form.id,
sapAjaxtarget: elementid,
postProcess: dhPostProcess});

}
catch(e)
{
ajaxObj = null;
}
if (ajaxObj != null)
{
try
{

if ( ajaxObj.executeRequest() ) {

returnvalue = true;
if (toDisable == true)
{

disableForm(ajaxObj.options.submittedFormId, true);

}
}

}
catch(e)
{
}
}
}
}
}
try{


if (th_runningInPopup()){
if (typeof WCFDialogAPI !== 'undefined' && WCFDialogAPI.isRunningInDialog){
window.opener = WCFDialogAPI.getOpener();
}else{
var getParent = getMainParent(window.parent);
window.opener = getParent.opener;
}
if (window.opener.thtmlbGetHostWindow && window.opener.thtmlbGetHostWindow().reset_last_server_update){
window.opener.thtmlbGetHostWindow().reset_last_server_update();
}
}else {
if(thtmlbGetHostWindow().reset_last_server_update){
thtmlbGetHostWindow().reset_last_server_update();
}
}
} catch(e) {}
return returnvalue;
}

// ========== preAjaxRequest ==========
function preAjaxRequest(target)
{
if (isAjaxEnabled == true)
{
ajax_submit = true;
if (target == null)
{
ajax_submit = false;
return;
}
if (target.length == 0)
{
ajax_submit = false;
return;
}
var element = document.getElementById("sap-ajaxtarget");
if (element != null)
{
element.value = target;
}else{
ajax_submit = false;
}
}
}

// ========== preAjaxRequest2 ==========
function preAjaxRequest2(target)
{
var element = document.getElementById("sap-ajax_dh_ssoptenabled");
if (element != null)
{
element.value = " ";
}
preAjaxRequest(target);
}

// ========== AjaxRequest ==========
function AjaxRequest(targerUrl, reqOptions){
this.url = targerUrl;
this.options = {method: "post",asynchronous: true, parameters: "", bindingMode: "xml", onComplete: AjaxCommon.emptyFunction, preProcess: AjaxCommon.preProcessFunction, postProcess: AjaxCommon.postProcessFunction, onFailure: AjaxCommon.onFailure};

this.onStateChange = onStateChange;
this.respondToReadyState = respondToReadyState;
this.getRequestObject = getRequestObject;
this.setOptions = setOptions;
this.responseIsSuccess = responseIsSuccess;
this.responseIsFailure = responseIsFailure;
this.processDefaultXML = processDefaultXML;
this.setRequestHeaders = setRequestHeaders;
this.requestHeaders = {};
this.request = this.getRequestObject();

if(!this.request){
throw 'Not able to create XmlHttpRequestObject object';
}
this.setOptions(reqOptions);
}

// ========== thtmlbNavigateToLogicalLink ==========
function thtmlbNavigateToLogicalLink(iv_link_id)
{
thtmlbSaveKeyboardFocus("first_active_element_in_work_area");
crmFrwNavigateToLogicalLink(iv_link_id, "KBD");
}

// ========== menu_navigate ==========
function menu_navigate(pagecontext, link){
var form = document.getElementsByTagName("FORM")[0];
if (form != null && typeof(htmlbSubmitLib) != 'undefined') {
htmlbSubmitLib("htmlb", this, "htmlb:link:click:null", form.id, pagecontext + "_" + link,link,1,"#");
}
}

// ========== isDeltaHandlingAutoMode ==========
function isDeltaHandlingAutoMode(){
var hiddenFlag = document.getElementById("sap-ajax_dh_mode");
if(hiddenFlag != null && hiddenFlag.value.toUpperCase() == "AUTO"){
return true;
}
return false;
}

// ========== setDeltaHandlingMode ==========
function setDeltaHandlingMode(mode){
var hiddenFlag = document.getElementById("sap-ajax_dh_mode");
if(hiddenFlag != null ){
hiddenFlag.value = mode;
}
}

// ========== cancelAjaxRequest ==========
function cancelAjaxRequest(){
isAjaxEnabled = false;
}

// ========== isAjaxActive ==========
function isAjaxActive()
{
if (isAjaxEnabled == false)
return false;
try
{
ajaxObj = new AjaxRequest('', {
method: 'post',
asynchronous: true,
parameters: '',
bindingMode: 'xml'
});
}
catch(ex)
{
return false;
}
return true;
}

// ========== htmlbSL ==========
function htmlbSL(elem,eventType_idx,objectID_plus_eventName,eventDef,param1,param2)
{
  // If this is a externally triggered roundtrip and if the thtmlbIsExternalRoundtrip is not
  // set by application, we will check the call-stack.
  thSetExternalRoundtripIfNotSet();

  eventType = htmlbEDIC[eventType_idx];
  paramCount = arguments.length>4 ? arguments.length-4 : 0;
  if(!eventDef) eventDef='null';
  eventType = eventType + ':' + eventDef;
  tokens = objectID_plus_eventName.split(':'); objectID=tokens[0]; eventName=tokens[1];
  frm_name=document.getElementById("htmlb_first_form_id").value;
  htmlbSubmitLib('htmlb',elem,eventType,frm_name,objectID,eventName,paramCount,param1,param2);

  return false;
}

// ========== htmlbEL ==========
function htmlbEL(elem,eventType_idx,objectID_plus_eventName,eventDef,param1,param2)
{
  eventType = htmlbEDIC[eventType_idx];
  paramCount = arguments.length>4 ? arguments.length-4 : 0;
  if(!eventDef) eventDef='null';
  eventType = eventType + ':' + eventDef;
  tokens = objectID_plus_eventName.split(':'); objectID=tokens[0]; eventName=tokens[1];
  eventClass = eventType.split(':')[2];
  frm_name=document.getElementById("htmlb_first_form_id").value;
  return htmlbEventLib('htmlb',elem,eventClass,eventType,frm_name,objectID,eventName,paramCount,param1,param2);
}

// ========== thtmlbGetFirstForm ==========
function thtmlbGetFirstForm()
{
var lr_result = null;
var lv_firstFormId;var lr_firstFormIdField = thtmlbGetElement(gc_firstFormIdField);
if (lr_firstFormIdField)
{
lv_firstFormId = lr_firstFormIdField.value;
lr_result = thtmlbGetElement(lv_firstFormId);
}return lr_result;
}

// ========== getRequestObject ==========
function getRequestObject(){
if(thtmlbGetRuntime) thtmlbStartRuntime("getRequestObject");
var result;
result = window.XMLHttpRequest ?
new XMLHttpRequest() : new ActiveXObject("MSXML2.XMLHTTP");
if(thtmlbGetRuntime) thtmlbStopRuntime("getRequestObject");
return result;
}

// ========== htmlbSubmit ==========
function htmlbSubmit(elem,
                     eventType,
                     formID,
                     objectID,
                     eventName,
                     paramCount,
                     param1,param2,param3,param4,param5,param6,param7,param8,param9)
{
  /* When the flex IMPGrid is OnDemand mode delta handling needs to waiting until the flex */
  /* finish the calculation process */
  if (th_flexRoundtripStatus == 'waiting'){
      /* When the calculation process finish we will call the back action. */
      if (eventName == th_flexAction){
          th_flexHoldAction = function(){htmlbSubmit(elem,
                       eventType,
                       formID,
                       objectID,
                       eventName,
                       paramCount,
                       param1,param2,param3,param4,param5,param6,param7,param8,param9)};
          thtmlbUnregisterOnLoad(th_flexHoldAction);
          thtmlbRegisterOnLoad(th_flexHoldAction);
          return;
        }
   }else if (th_flexRoundtripStatus == 'actionExec'){
        /* In case no calculation process is executed, we execute the action immediately */
        if (eventName == th_flexAction){
          th_flexRoundtripStatus = '';
          th_flexAction = '';
          frm_name=document.getElementById("htmlb_first_form_id").value;
          htmlbSubmitLib('htmlb',elem,eventType,frm_name,objectID,eventName,'0');
        }
   }else if (th_flexHoldAction){
        /* After, execute the action we reset the variables */
        thtmlbUnregisterOnLoad(th_flexHoldAction);
        th_flexHoldAction = '';
   }

 if(thtmlbGetRuntime) thtmlbStartRuntime("htmlbSubmit");

 if (document.getElementById(formID + "_complete").getAttribute("code") != "OK") return;

  var form = document.getElementById(formID);
  var func = window["doValidate_" + formID];
  if(func != null){
    var isValidate = true;
    isValidate = func();
    if(isValidate==false){
      if(document.all && event != null)
    event.returnValue = false;
      return false;
    }
  }
  // Saving some event parms for external reference
  thLast_objectID  = objectID;
  thLast_eventName = eventName;

  thtmlbRunScriptBeforeSubmit();

  form.htmlbScrollX.value = document.body.scrollLeft;
  form.htmlbScrollY.value = document.body.scrollTop;
  form.htmlbevt_ty.value = eventType;
  form.htmlbevt_oid.value = objectID;
  form.htmlbevt_id.value = eventName;
  form.htmlbevt_cnt.value = paramCount;
  if ( paramCount > 0 ) {
    form.htmlbevt_par1.value = param1;
  }else{
    form.htmlbevt_par1.value = "";
  };
  if ( paramCount > 1 ) {
    form.htmlbevt_par2.value = param2;
  }else{
    form.htmlbevt_par2.value = "";
  };
  if ( paramCount > 2 ) {
    form.htmlbevt_par3.value = param3;
  }else{
    form.htmlbevt_par3.value = "";
  };
  if ( paramCount > 3 ) {
    form.htmlbevt_par4.value = param4;
  }else{
    form.htmlbevt_par4.value = "";
  };
  if ( paramCount > 4 ) {
    form.htmlbevt_par5.value = param5;
  }else{
    form.htmlbevt_par5.value = "";
  };
  if ( paramCount > 5 ) {
    form.htmlbevt_par6.value = param6;
  }else{
    form.htmlbevt_par6.value = "";
  };
  if ( paramCount > 6 ) {
    form.htmlbevt_par7.value = param7;
  }else{
    form.htmlbevt_par7.value = "";
  };
  if ( paramCount > 7 ) {
    form.htmlbevt_par8.value = param8;
  }else{
    form.htmlbevt_par8.value = "";
  };
  if ( paramCount > 8 ) {
    form.htmlbevt_par9.value = param9;
  }else{
    form.htmlbevt_par9.value = "";
  };

  if(document.all)
  {
    if ( event != null )
      event.returnValue = false;
  }

  if (HTMLB_SECTION508){
   if(document.all)
      try{form.activeElement508.value = document.activeElement.getAttribute("id");}catch(ex){}
  }



  try { sap_htmlb_ofcsavescrol(); } catch(e) {}
  try { htmlbSubmitPre(); } catch(e) {}
  htmlbDisableFields();
  var l_answer=true;
  l_answer=htmlbSubmitForm(form);

  if(thtmlbGetRuntime) thtmlbStopRuntime("htmlbSubmit");

  if(l_answer==false){return l_answer;}
  htmlbEnableFields();
  try { htmlbSubmitPost(); } catch(e) {}

  func = window["clearUp_" + formID];
  if(func != null){
    var isClearUp = true;
    isClearUp = func();
    if(isClearUp==false){
      event.returnValue = false;
      return false;
    }
  }

  form.htmlbevt_ty.value = "";
  form.htmlbevt_oid.value = "";
  form.htmlbevt_id.value = "";
  form.htmlbevt_cnt.value = 0;
  form.htmlbevt_par1.value = "";
  form.htmlbevt_par2.value = "";
  form.htmlbevt_par3.value = "";
  form.htmlbevt_par4.value = "";
  form.htmlbevt_par5.value = "";
  form.htmlbevt_par6.value = "";
  form.htmlbevt_par7.value = "";
  form.htmlbevt_par8.value = "";
  form.htmlbevt_par9.value = "";
}

// ========== htmlbSubmitForm ==========
function htmlbSubmitForm(form) {
if (processDataLossDialog() == false ) {
return;
}
if (submissionInProgress == true) {
return;
}
submissionInProgress = true;




if(document.all) {
docHeight=document.body.clientHeight;
docWidth=document.body.clientWidth;
docTop=document.body.scrollTop;
docLeft=document.body.scrollLeft;
}else{
docHeight=window.innerHeight;
docWidth=window.innerWidth;
}



thSaveKbSelect();









try {
var activeElement = document.activeElement;
if (activeElement && activeElement.nodeName == "INPUT" && activeElement.onchange) {
activeElement.onchange();
}
} catch(e) {}



thPrevDocTitle = document.title;


thUpdateFocusElementInfo();

var submitHappened = htmlbSubmitFormAjax(form);
if (submitHappened == false)
{
try {
form.submit();


showSubmitInProgress(true);
if (toDisable == true) {
disableForm(form.id, true);
}
}
catch (e) {
showSubmitInProgress(false);
submissionInProgress = false;

}
}else{
showSubmitInProgress(true);
}
}

// ========== htmlbEvent ==========
function htmlbEvent(elem,
                    eventClass,
                    eventType,
                    formID,
                    objectID,
                    eventName,
                    paramCount,
                    param1,param2,param3,param4,param5,param6,param7,param8,param9)
{
 var htmlbevent = htmlbCreateEvent(elem,formID+" "+objectID,eventName);

  if(htmlbEventFunction==null)
    htmlbEventFunction = window[formID+"_"+objectID+"_"+eventClass];
  if ( htmlbEventFunction != null) htmlbEventFunction(htmlbevent);
  htmlbEventFunction=null;

  if(htmlbevent.cancelSubmit==false){
    htmlbSubmit(elem,eventType,formID,objectID,eventName,paramCount,param1,param2,param3,param4,param5,param6,param7,param8,param9);
  }
  return htmlbevent.returnValue;
}

// ========== htmlbEventLib ==========
function htmlbEventLib(library,elem,eventClass,eventType,formID,objectID,eventName,paramCount,param1,param2,param3,param4,param5,param6,param7,param8,param9)
{
  document.forms[formID].onInputProcessing.value = library;
  return htmlbEvent(elem,eventClass,eventType,formID,objectID,eventName,paramCount,param1,param2,param3,param4,param5,param6,param7,param8,param9)
}

// ========== deltaRenderingCallback ==========
function deltaRenderingCallback(reqObj){
if (reqObj.request.readyState < 4){
return;
}
if (thtmlbGetRuntime) {
thtmlbWrite("-------------PBO","blue");
thtmlbSetPAIStart();
}

var httpredirect = reqObj.request.getResponseHeader("sap-ajax_http_redirect");
var responseText = reqObj.request.responseText;

if ( reqObj.request.status != 200 ) {
showSubmitInProgress(false);
submissionInProgress = false;
thtmlbWrite("Error in deltaRenderingCallback: reqObj.request.status is " + reqObj.request.status);
}


if ( responseText == "" ) {
var tmpWarningText = "";

tmpWarningText = tmpWarningText + "Warning: empty AJAX response received.\n\n";

tmpWarningText = tmpWarningText + "reqObj.options.parameters:\n";
tmpWarningText = tmpWarningText + reqObj.options.parameters + "\n\n";

tmpWarningText = tmpWarningText + "reqObj.options.sapAjaxtarget:\n";
tmpWarningText = tmpWarningText + reqObj.options.sapAjaxtarget + "\n\n";

tmpWarningText = tmpWarningText + "reqObj.options.submittedFormId:\n";
tmpWarningText = tmpWarningText + reqObj.options.submittedFormId + "\n\n";

thtmlbWrite(tmpWarningText);

}



if(thtmlbGetRuntime) thtmlbStartRuntime("deltaRenderingCallback");

if(httpredirect != "X") {

if (responseText.indexOf('rootAreaDiv') < 0) {

showSubmitInProgress(false);

submissionInProgress = false;
var escapedText = responseText.replace(/'/gi, "\'");

if ( responseText == "" ) {

if ( gv_thtmlb_JS_debug_mode == "EMPTY_AJAX_WARNING" ) {
alert(tmpWarningText);
}

return;
}




if (thtmlbUtil.getBrowser() == isIE && thtmlbUtil.getBrowserDetails().version >= 9) {
if (reqObj.request.status == 500) {
return;
}
}

var parentDoc = null;
if(thtmlbIsRunningInPortal()) {
parentDoc = document;
} else {
parentDoc = parent.document;
}

parentDoc.write(escapedText);
parentDoc.close();
return;
};

var targets = reqObj.options.sapAjaxtarget;
if(isDeltaHandlingAutoMode()){
var httpHeaderDefinedTargets = reqObj.request.getResponseHeader("sap-ajax-targets");
targets = httpHeaderDefinedTargets;
}
if (targets == null){
targets = "";
}
var elementids = targets.split(",");
try{
crmFrwRemoveScrollAreaEvent();
}catch(except){}

var targetsInfo = new Array();
for (var i = 0, len = elementids.length; i < len; i++){
var elementid = elementids[i];
if(elementid != ""){
var anInfo = new Object();
anInfo.targetName = elementid;
var endstr = "<!-- " + elementid + " -->";
var beginstr = "<!-- Begin " + elementid + " -->";
anInfo.begin = responseText.indexOf(beginstr);
anInfo.end = responseText.indexOf(endstr, index1);
anInfo.beginStrLength = beginstr.length;
targetsInfo[i] = anInfo;
}
}
targetsInfo = optimizeTargets(targetsInfo);

var tiLength = targetsInfo.length;
if(thtmlbGetRuntime) thtmlbStartRuntime("response processing");

if(gv_tajaxDHUseJsRegex == "X") {
drcJsRegex(reqObj, tiLength, targetsInfo, responseText);
}
else{

for (var i = 0; i < tiLength; i++){

var startElement = new Date();
var elementid = targetsInfo[i].targetName;
var index1 = targetsInfo[i].begin;
var index2 = targetsInfo[i].end;
var afterIndexLocation = new Date();
var afterSubstring = null;
var afterReplacement = null;
var beforeReplacement = null;
var afterScripts = null;

if (index1 > 0 && index2 > index1){
var preformattedAreaString = responseText.substring(index1 + targetsInfo[i].beginStrLength, index2);
afterSubstring = new Date();
var el = th$(elementid);
if (el){
if ( isSkipUpdateAjaxAreaForExtRndTrip(el, responseText) ) {
thtmlbWrite("Skipping User-modified AjaxArea id=" + el.id);


thtmlbSuppressOnLoadKeyboardFocus();
} else {

var firstLinkBlock = -1;
var abLength = 0;

var perfResponse=preformattedAreaString;
allBlocks = extractArrayOfIndexes(preformattedAreaString);
if(allBlocks) {
abLength = allBlocks.length;
}
if(abLength>0) {
perfResponse=preformattedAreaString.substring(0, allBlocks[0][1]);
}

var renderedResponse = perfResponse;


for(var blockCounter=0; blockCounter<abLength; blockCounter++) {
if(allBlocks[blockCounter][0]==4) {
firstLinkBlock = blockCounter;
break;
}
}

if(thtmlbGetRuntime) thtmlbStartRuntime("/preprocessing");
if(thtmlbGetRuntime) thtmlbStartRuntime("//scripts");

beforeReplacement = new Date();
afterReplacement = new Date();

var aScript = "";
var cutScript = "";
var aLib = "";


if(gv_tajaxDHScriptMode!='NOAGGREGATION') {

var previouslyCumulatedInlineScripts = new Array();

for(var j=0; j<abLength; j++) {
if(allBlocks[j][0]>2) {
break;
}
if(allBlocks[j][0]==1) {
cutScript = preformattedAreaString.substr(allBlocks[j][3], allBlocks[j][4]) + ";";
aLib = "";
previouslyCumulatedInlineScripts.push(cutScript);
}
else if (allBlocks[j][0]==2) {



if (previouslyCumulatedInlineScripts.length>0) {

thtmlbAddPendingScriptForAjaxTarget(elementid, null,
previouslyCumulatedInlineScripts.join(";"));

previouslyCumulatedInlineScripts = new Array();
}
aLib = preformattedAreaString.substr(allBlocks[j][3], allBlocks[j][4]);
cutScript = "";


if (aLib != ""){
thtmlbAddPendingScriptForAjaxTarget(elementid, aLib, null);
}
}
}



if (previouslyCumulatedInlineScripts.length>0) {

thtmlbAddPendingScriptForAjaxTarget(elementid, null,
previouslyCumulatedInlineScripts.join(";"));

previouslyCumulatedInlineScripts = new Array();
}
if(thtmlbGetRuntime) thtmlbStopRuntime("//scripts add");

} else {

for(var j=0; j<abLength; j++) {
if(allBlocks[j][0]>2) {
break;
}
if(allBlocks[j][0]==1) {
cutScript = preformattedAreaString.substr(allBlocks[j][3], allBlocks[j][4]) + ";";
aLib = "";
}
else if (allBlocks[j][0]==2) {
aLib = preformattedAreaString.substr(allBlocks[j][3], allBlocks[j][4]);
cutScript = "";
}
aScript = aScript + cutScript;

if (aLib != ""){
thtmlbAddPendingScriptForAjaxTarget(elementid, aLib, null);
}
else {
thtmlbAddPendingScriptForAjaxTarget(elementid, null, cutScript);
}
if(thtmlbGetRuntime) thtmlbStopRuntime("//scripts add");
}
}

afterScripts = new Date();
if(thtmlbGetRuntime) thtmlbStopRuntime("//scripts");
if (isProfileMode) {
var scriptExecution = afterScripts - afterReplacement;
var replacement = afterReplacement - beforeReplacement;
var scriptReplacement = beforeReplacement - afterSubstring;
var substringOperation = afterSubstring - afterIndexLocation;
var indexLocation = afterIndexLocation - startElement;
}
if(thtmlbGetRuntime) thtmlbStartRuntime("//inline styles");

var aStyle = "";

for(var blockCounter=0; blockCounter<abLength; blockCounter++) {
if(allBlocks[blockCounter][0]==3) {
aStyle = aStyle
+ preformattedAreaString.substr(allBlocks[blockCounter][3],
allBlocks[blockCounter][4])
+ " ";
}
}
var browser = thtmlbUtil.getBrowserAdvanced();
if (browser.browser === 'IE' && browser.version < 10) {
if(thtmlbGetRuntime) thtmlbStartRuntime("//styles add");
if(aStyle!="") {

thtmlbLoadInlineStyle(aStyle);
}
if(thtmlbGetRuntime) thtmlbStopRuntime("//styles add");
}
else {
if(aStyle!="") {


renderedResponse = "<style type=\"text/css\">"
+ aStyle + "</style>" + renderedResponse;
}
}

if(thtmlbGetRuntime) thtmlbStopRuntime("//inline styles");
if(thtmlbGetRuntime) thtmlbStartRuntime("//external styles");

if(firstLinkBlock>-1) {
for(var blockCounter=firstLinkBlock; blockCounter<abLength; blockCounter++) {
aLib = preformattedAreaString.substr(allBlocks[blockCounter][3],
allBlocks[blockCounter][4]);
if (aLib != ""){
thtmlbLoadCSS(aLib);
}
}
}



if(thtmlbGetRuntime) thtmlbStopRuntime("/preprocessing");

if(thtmlbGetRuntime) thtmlbStartRuntime("/innerHTML replacement "+elementid);


if (el.tagName=="TR") {
tajaxTableRowReplace(el,renderedResponse);
} else {


if(el && el.contains && document.activeElement && el.contains(document.activeElement) &&
(document.activeElement.nodeName == "INPUT" || document.activeElement.nodeName == "TEXTAREA")){
if (document.activeElement.getAttribute('type') != "checkbox" && document.activeElement.getAttribute('type') != "radio"){
if (typeof(document.activeElement.selectionStart) == "number") {
document.activeElement.selectionEnd = document.activeElement.selectionStart;
}
}
}


renderedResponse = "<DIV STYLE='DISPLAY:NONE;'>&NBSP;<!--IEFIX--></DIV>" + renderedResponse;
replaceInnerHTML(el, renderedResponse);
}

if(thtmlbGetRuntime) thtmlbStopRuntime("/innerHTML replacement "+elementid);

thtmlbCollectSize(renderedResponse,elementid);

if(thtmlbGetRuntime) thtmlbStartRuntime("/postprocessing");

thtmlbLoadNextPendingScriptForAjaxTarget(elementid);

if(thtmlbGetRuntime) thtmlbStopRuntime("/postprocessing");
}
}
}
}
}

if(thtmlbGetRuntime) thtmlbStopRuntime("response processing");

showSubmitInProgress(false);



submissionInProgress = false;
if (toDisable == true)
{
disableForm(reqObj.options.submittedFormId, false);
}
if(typeof(adjustNavbar) != "undefined"){
thtmlbSCHeightIsValid = false;
adjustNavbar();
}
try{
crmFrwAddScrollAreaEvent();
}catch(excpt){}

} else {
try{

var location = reqObj.request.getResponseHeader("location");
if(location == "") location = window.location.href.split("#")[0];

var secondFrame = parent.document.getElementById("WorkAreaFrame2");
if(secondFrame && secondFrame.getAttribute("fsInit") == "loaded") {

var targetName = window.name;
if (targetName.indexOf("WorkAreaFrame1") != -1)
targetName = targetName.replace("WorkAreaFrame1", "WorkAreaFrame2");
else
targetName = targetName.replace("WorkAreaFrame2", "WorkAreaFrame1");

parent.frames[targetName].location.replace(location);
return;
} else {
window.location.replace(location);
}
if (toDisable == true){
disableForm(actualForm.id, true);
}
}catch (e){
showSubmitInProgress(false);
submissionInProgress = false;
thtmlbShieldDrop('all__shield');

}
}



thtmlbReinitGlobalVars();
try{

setTimeout(thtmlbTriggerOnloadAJAX, 0);
}catch(excpt){}

thtmlbShieldDrop('all__shield');


if(thtmlbGetRuntime) {
thtmlbStopRuntime("deltaRenderingCallback");
thtmlbSetAJAXPAIEnd();
thtmlbShowSize();
thtmlbWriteRuntime(reqObj);
}
}

// ========== thtmlbRoundtripFinalStepAJAX ==========
function thtmlbRoundtripFinalStepAJAX() {

if (thtmlbIsExternalRoundtrip) {
thtmlbIsExternalRoundtrip = false;
}




if (thtmlbIsKeyboardFocusSuppressedOnLoad() == true) {
gv_thtmlbSuppressKeyboardFocus = false;
thtmlbFocus = null;
thtmlbSaveKeyboardFocus("thtmlbSuppressKeyboardFocus");

}
}

// ========== thtmlbTriggerOnloadAJAX ==========
function thtmlbTriggerOnloadAJAX() {
if(thtmlbGetRuntime) thtmlbStartRuntime("registered onload handlers");

var scriptsToExecute = ajaxOnloadFuncs.slice(0); 
var lv_stelength = scriptsToExecute.length;
var lv_reallength = 0;
for (var i=0;i<lv_stelength;i++) {
try{


if(thtmlbArrayContains(ajaxOnloadFuncs, scriptsToExecute[i])) {
lv_reallength++;
var stringref = "";
if(thtmlbGetRuntime) {
var funccode = "onload: " + scriptsToExecute[i].ref;
stringref = funccode.split("{")[0];
if (stringref.search(/onload:\s+function\s*\(/) > -1) {
stringref = funccode.substr(0,200);
}

}

if(thtmlbGetRuntime) thtmlbStartRuntime(stringref);
if (scriptsToExecute[i].ref) scriptsToExecute[i].ref();
if(thtmlbGetRuntime) thtmlbStopRuntime(stringref);
}
} catch(e) {}
}







thtmlbRoundtripFinalStepAJAX();

if(thtmlbGetRuntime) thtmlbStopRuntime("registered onload handlers");
}