// Auto-injected metadata for GeocodeAgent
const nodeMetadata = {
  "type": "GeocodeAgent",
  "label": "Geocode Agent",
  "icon": "MapPinned",
  "color": "bg-teal-600",
  "description": "Requires extracted places: PlaceExtract output, or an input whose documents already include `locations`. Uses multiple geocoders to turn extracted locations into map-ready coordinates. Optionally use cache to reduce lookups and ensure consistency.",
  "category": "enrichment",
  "requiredUpstreamNodes": [
    "PlaceExtract"
  ],
  "satisfiedByInputData": "locations",
  "dependencyHelperText": "Requires extracted places as input: Place Extract, or saved places from an input.",
  "inputs": [
    {
      "id": "locations",
      "label": "Locations",
      "type": "array",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "places",
      "label": "Places",
      "type": "object"
    },
    {
      "id": "text",
      "label": "Text",
      "type": "string"
    }
  ],
  "defaultParams": {
    "maxLocations": 200,
    "perLocationTimeout": 300,
    "useCache": true,
    "stylebookApiUrl": "",
    "projectSlug": "",
    "evaluationModel": "",
    "geographicReasoningModel": "",
    "geographicEstimationModel": "",
    "routerModel": "",
    "evaluationAiModelConfigId": null,
    "geographicReasoningAiModelConfigId": null,
    "geographicEstimationAiModelConfigId": null,
    "routerAiModelConfigId": null,
    "useCacheLlmAdjudication": true,
    "useCacheLlmAdjudicationOnMissRecall": false,
    "webSearchProvider": "auto"
  }
};

/**
 * Geocode geography is reviewed and edited on the processed-item **Review** tab.
 * We intentionally omit a second Leaflet map on the Visualizations tab.
 */
export function buildVisualization(
  _nodeId: string,
  _nodeLabel: string,
  _output: unknown,
): null {
  return null
}
