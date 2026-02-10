FUNCTION_BLOCK Test_Block
   VAR
        values : ARRAY [1..10] OF BOOL;
        count : INT;
        test1: BOOL;
    END_VAR
    BEGIN
        values[1] := TRUE;
        values[2] := FALSE;
        values[3] := FALSE;
        values[4] := FALSE;
        values[5] := FALSE;
        values[6] := FALSE;
        values[7] := FALSE;
        values[8] := FALSE;
        values[9] := FALSE;
        values[10] := FALSE;
    END_BEGIN

    METHOD PUBLIC Delete
        BEGIN
            IF THIS^.test1 THEN
                THIS^.values[3] := TRUE;
                Count := Count + 1;
            END_IF
        END_BEGIN
    END_METHOD

END_FUNCTION_BLOCK