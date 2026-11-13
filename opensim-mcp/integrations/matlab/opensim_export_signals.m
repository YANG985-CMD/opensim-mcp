function manifestPath = opensim_export_signals(data, outputFolder, options)
%OPENSIM_EXPORT_SIGNALS Export explicit timetable signals for the OpenSim viewer.
% Row times must be durations. Declare VariableUnits for every numeric column.
% Example:
%   opensim_export_signals(TT, "E:\study\signals", ...
%       Source="MATLAB simulation", Interpolation="linear", ...
%       MaxGapSeconds=0.02, Components=bindings)
% No resampling, missing-data filling, angle conversion or clock fitting occurs.
arguments
    data timetable
    outputFolder (1,1) string
    options.Source (1,1) string = "MATLAB"
    options.Components (1,1) struct = struct()
    options.Interpolation (1,1) string {mustBeMember(options.Interpolation,["none","linear","previous"])} = "none"
    options.MaxGapSeconds (1,1) double = NaN
    options.TimeOffsetSeconds (1,1) double = 0
end
assert(height(data) >= 2 && height(data) <= 20000, 'Need 2..20000 signal samples.');
assert(width(data) >= 1 && width(data) <= 32, 'Need 1..32 signal variables.');
assert(isduration(data.Properties.RowTimes), 'Use explicit duration row times; convert datetimes relative to your chosen origin first.');
time = seconds(data.Properties.RowTimes);
assert(all(isfinite(time)) && all(diff(time) > 0), 'Time samples must be finite and strictly increasing.');
assert(isfinite(options.MaxGapSeconds) && options.MaxGapSeconds > 0, 'Provide an explicit positive MaxGapSeconds.');
assert(isfinite(options.TimeOffsetSeconds), 'TimeOffsetSeconds must be finite.');
assert(strlength(options.Source) > 0, 'Source must identify the data origin.');
names = data.Properties.VariableNames;
assert(~ismember('time_s', names), 'time_s is reserved for the exported time column.');
assert(all(ismember(fieldnames(options.Components), names)), 'Bindings must identify existing timetable variables.');
csvPath = fullfile(outputFolder, 'signals.csv');
manifestPath = fullfile(outputFolder, 'signals.json');
assert(~isfile(csvPath) && ~isfile(manifestPath), 'Refusing to overwrite an existing signal export.');
output = table(time, VariableNames={'time_s'});
channels = cell(1, width(data));
for index = 1:width(data)
    name = names{index};
    values = data.(name);
    assert((isnumeric(values) || islogical(values)) && isreal(values) && iscolumn(values) && all(isfinite(values)), ...
        'Each signal must be a real, finite numeric column; missing values are not filled.');
    unit = string(data.Properties.VariableUnits{index});
    assert(strlength(unit) > 0, 'Declare VariableUnits for every signal, using "1" for dimensionless data.');
    label = string(data.Properties.VariableDescriptions{index});
    if strlength(label) == 0
        label = string(name);
    end
    channel = struct('column', string(name), 'label', label, 'unit', unit);
    if isfield(options.Components, name)
        binding = options.Components.(name);
        assert(isstruct(binding) && isequal(sort(fieldnames(binding)), {'kind';'name'}), 'A component binding needs kind and name.');
        assert(ismember(string(binding.kind), ["body","frame","muscle","coordinate","marker"]), 'Unknown binding kind.');
        channel.component = binding;
    end
    channels{index} = channel;
    output.(name) = values;
end
if ~isfolder(outputFolder)
    mkdir(outputFolder);
end
writetable(output, csvPath, Encoding='UTF-8', Delimiter=',');
manifest = struct('schema', 'opensim_signal_source_v1', 'path', csvPath, 'label', options.Source, ...
    'time_column', 'time_s', 'time_unit', 's', 'time_offset_s', options.TimeOffsetSeconds, ...
    'interpolation', options.Interpolation, 'max_gap_s', options.MaxGapSeconds, 'channels', {channels});
writestruct(manifest, manifestPath);
roundtrip = readtable(csvPath, TextType='string', VariableNamingRule='preserve');
assert(height(roundtrip) == height(data) && width(roundtrip) == width(data)+1, 'Export row/column validation failed.');
assert(max(abs(roundtrip.time_s-time)) < 1e-9, 'Export time readback differs from the input.');
fprintf('Exported %d samples, %d channels: %s\n', height(data), width(data), manifestPath);
end
